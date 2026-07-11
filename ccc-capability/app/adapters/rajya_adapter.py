from __future__ import annotations
from typing import Any
from app.adapters.base import CapabilityAdapterBase
from app.capability.events import CapabilityEvent, EventType

DESTRUCTIVE_EVENTS = {EventType.DOCUMENT_DELETED}


class PolicyFlag:
    def __init__(self, event_id: str, rule: str, detail: str):
        self.event_id = event_id
        self.rule = rule
        self.detail = detail

    def to_dict(self) -> dict:
        return {"event_id": self.event_id, "rule": self.rule, "detail": self.detail}


class RajyaAdapter(CapabilityAdapterBase):
    name = "rajya"

    def __init__(self):
        super().__init__()
        self._audit_trail: list[dict[str, Any]] = []
        self._flags: list[PolicyFlag] = []

    def _process(self, event: CapabilityEvent) -> dict[str, Any]:
        self._audit_trail.append(event.to_execution_metadata())

        if event.event_type in DESTRUCTIVE_EVENTS and event.actor_id is None:
            flag = PolicyFlag(
                event_id=event.event_id,
                rule="destructive_action_requires_actor",
                detail=f"{event.event_type.value} on {event.entity_type}:{event.entity_id} has no actor_id",
            )
            self._flags.append(flag)
            return {"status": "audited", "policy_flag": flag.to_dict()}

        return {"status": "audited", "policy_flag": None}

    def audit_trail(self) -> list[dict]:
        return list(self._audit_trail)

    def flags(self) -> list[dict]:
        return [f.to_dict() for f in self._flags]

    def is_healthy(self, flag_threshold: int = 50) -> bool:
        return len(self._flags) < flag_threshold
