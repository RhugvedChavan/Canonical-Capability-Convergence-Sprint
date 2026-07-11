from __future__ import annotations

import dataclasses
import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Optional, Protocol, runtime_checkable

logger = logging.getLogger("capability.events")


def _default_module_identifier() -> str:
    """Sourced from the manifest at call time (not import time) so events
    always reflect the single source of truth in capability.manifest.json
    instead of a second, independently-maintained literal that could drift."""
    from app.capability.manifest import load_manifest

    return load_manifest().module_identifier


def _default_capability_version() -> str:
    from app.capability.manifest import load_manifest

    return load_manifest().capability_version


class EventType(str, Enum):
    DOCUMENT_CREATED = "document_created"
    DOCUMENT_UPDATED = "document_updated"
    VERSION_RESTORED = "version_restored"
    COMMENT_ADDED = "comment_added"
    TASK_CREATED = "task_created"
    TASK_UPDATED = "task_updated"
    TASK_COMPLETED = "task_completed"
    DOCUMENT_DELETED = "document_deleted"
    DOCUMENT_UPLOADED = "document_uploaded"


@dataclass(frozen=True)
class CapabilityEvent:
    event_type: EventType
    entity_type: str
    entity_id: Optional[int]
    actor_id: Optional[int]
    payload: dict[str, Any]
    module_identifier: str = field(default_factory=_default_module_identifier)
    capability_version: str = field(default_factory=_default_capability_version)
    schema_version: str = "1.0"
    correlation_id: Optional[str] = None
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    occurred_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    # Assigned by EventBus.dispatch() at dispatch time (not construction
    # time), giving every event a total, deterministic order even if two
    # events share the same occurred_at timestamp — important for replay
    # consumers that need a stable ordering, not just a stable identity.
    sequence: Optional[int] = None

    def to_execution_metadata(self) -> dict[str, Any]:
        """The structured, serializable form every adapter and every replay
        consumer receives. This is the on-the-wire event contract."""
        return {
            "event_id": self.event_id,
            "sequence": self.sequence,
            "event_type": self.event_type.value,
            "occurred_at": self.occurred_at,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "actor_id": self.actor_id,
            "payload": self.payload,
            "module_identifier": self.module_identifier,
            "capability_version": self.capability_version,
            "schema_version": self.schema_version,
            "correlation_id": self.correlation_id,
        }


@runtime_checkable
class CapabilityAdapter(Protocol):
    name: str

    def handle_event(self, event: CapabilityEvent) -> dict[str, Any]:
        ...


@dataclass
class AdapterOutcome:
    adapter_name: str
    ok: bool
    detail: Any = None
    error: Optional[str] = None


@dataclass
class DispatchReport:
    event: CapabilityEvent
    outcomes: list[AdapterOutcome] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "event": self.event.to_execution_metadata(),
            "outcomes": [
                {"adapter": o.adapter_name, "ok": o.ok, "detail": o.detail, "error": o.error}
                for o in self.outcomes
            ],
        }


BeforeHook = Callable[[CapabilityEvent], Optional[CapabilityEvent]]
AfterHook = Callable[[CapabilityEvent, list[AdapterOutcome]], None]


class EventBus:
    """Central dispatch point. Adapters register themselves here; routers
    call emit() after every successful state change."""

    def __init__(self):
        self._adapters: list[CapabilityAdapter] = []
        self._before_hooks: list[BeforeHook] = []
        self._after_hooks: list[AfterHook] = []
        self._log: list[DispatchReport] = []
        self._sequence_lock = threading.Lock()
        self._next_sequence = 1

    def register_adapter(self, adapter: CapabilityAdapter) -> None:
        self._adapters.append(adapter)
        logger.info("adapter_registered", extra={"adapter": adapter.name})

    def unregister_adapter(self, name: str) -> None:
        self._adapters = [a for a in self._adapters if a.name != name]

    def add_before_hook(self, hook: BeforeHook) -> None:
        self._before_hooks.append(hook)

    def add_after_hook(self, hook: AfterHook) -> None:
        self._after_hooks.append(hook)

    @property
    def adapters(self) -> list[CapabilityAdapter]:
        return list(self._adapters)

    @property
    def replay_log(self) -> list[dict]:
        return [r.to_dict() for r in self._log]

    def emit(
        self,
        event_type: EventType,
        entity_type: str,
        entity_id: Optional[int],
        actor_id: Optional[int],
        payload: dict[str, Any],
        correlation_id: Optional[str] = None,
    ) -> DispatchReport:
        event = CapabilityEvent(
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_id=actor_id,
            payload=payload,
            correlation_id=correlation_id,
        )
        return self.dispatch(event)

    def dispatch(self, event: CapabilityEvent) -> DispatchReport:
        with self._sequence_lock:
            seq = self._next_sequence
            self._next_sequence += 1
        event = dataclasses.replace(event, sequence=seq)

        for hook in self._before_hooks:
            maybe = hook(event)
            if maybe is None:
                logger.info("event_vetoed", extra={"event_id": event.event_id})
                report = DispatchReport(event=event, outcomes=[])
                self._log.append(report)
                return report
            event = maybe

        outcomes: list[AdapterOutcome] = []
        for adapter in self._adapters:
            try:
                detail = adapter.handle_event(event)
                outcomes.append(AdapterOutcome(adapter_name=adapter.name, ok=True, detail=detail))
            except Exception as exc:  # isolate adapter failures from each other and the caller
                logger.error(
                    "adapter_dispatch_failed",
                    extra={"adapter": adapter.name, "event_id": event.event_id, "error": str(exc)},
                )
                outcomes.append(AdapterOutcome(adapter_name=adapter.name, ok=False, error=str(exc)))

        report = DispatchReport(event=event, outcomes=outcomes)
        self._log.append(report)
        for hook in self._after_hooks:
            hook(event, outcomes)
        return report


# Process-wide singleton event bus used by routers and adapters.
event_bus = EventBus()
