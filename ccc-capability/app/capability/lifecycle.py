from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Optional

logger = logging.getLogger("capability.lifecycle")


class LifecycleState(str, Enum):
    UNREGISTERED = "UNREGISTERED"
    REGISTERED = "REGISTERED"
    INITIALIZING = "INITIALIZING"
    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"
    DEPRECATING = "DEPRECATING"
    RETIRED = "RETIRED"


# Explicit allow-list of legal transitions. Anything not listed here is
# rejected by transition_to(), which is what makes this "deterministic" —
# behavior never depends on incidental call order.
_ALLOWED_TRANSITIONS: dict[LifecycleState, set[LifecycleState]] = {
    LifecycleState.UNREGISTERED: {LifecycleState.REGISTERED},
    LifecycleState.REGISTERED: {LifecycleState.INITIALIZING},
    LifecycleState.INITIALIZING: {LifecycleState.ACTIVE, LifecycleState.DEGRADED},
    LifecycleState.ACTIVE: {LifecycleState.DEGRADED, LifecycleState.DEPRECATING},
    LifecycleState.DEGRADED: {LifecycleState.ACTIVE, LifecycleState.DEPRECATING},
    LifecycleState.DEPRECATING: {LifecycleState.RETIRED},
    LifecycleState.RETIRED: set(),
}


class IllegalLifecycleTransition(Exception):
    def __init__(self, current: LifecycleState, target: LifecycleState):
        self.current = current
        self.target = target
        super().__init__(
            f"Illegal lifecycle transition: {current.value} -> {target.value}. "
            f"Allowed from {current.value}: "
            f"{sorted(s.value for s in _ALLOWED_TRANSITIONS.get(current, set()))}"
        )


class LifecycleEvent:
    def __init__(self, previous: LifecycleState, current: LifecycleState, reason: str):
        self.transition_id = str(uuid.uuid4())
        self.previous = previous
        self.current = current
        self.reason = reason
        self.timestamp = datetime.now(timezone.utc)

    def to_dict(self) -> dict:
        return {
            "transition_id": self.transition_id,
            "previous_state": self.previous.value,
            "current_state": self.current.value,
            "reason": self.reason,
            "timestamp": self.timestamp.isoformat(),
        }


class LifecycleManager:
    """Owns the single authoritative lifecycle state for this capability instance."""

    def __init__(self):
        self._state = LifecycleState.UNREGISTERED
        self._history: list[LifecycleEvent] = []
        self._listeners: list[Callable[[LifecycleEvent], None]] = []
        # Guards state mutation so concurrent callers (e.g. a health check
        # and an inbound webhook both reacting to a dependency outage at
        # once) can never race into an inconsistent state or duplicate
        # history entries.
        self._lock = threading.Lock()

    @property
    def state(self) -> LifecycleState:
        return self._state

    @property
    def history(self) -> list[dict]:
        return [e.to_dict() for e in self._history]

    def on_transition(self, listener: Callable[[LifecycleEvent], None]) -> None:
        self._listeners.append(listener)

    def can_transition_to(self, target: LifecycleState) -> bool:
        return target in _ALLOWED_TRANSITIONS.get(self._state, set())

    def transition_to(self, target: LifecycleState, reason: str = "") -> LifecycleEvent:
        with self._lock:
            if not self.can_transition_to(target):
                raise IllegalLifecycleTransition(self._state, target)
            event = LifecycleEvent(previous=self._state, current=target, reason=reason)
            self._state = target
            self._history.append(event)
        logger.info(
            "lifecycle_transition",
            extra={
                "transition_id": event.transition_id,
                "previous": event.previous.value,
                "current": event.current.value,
                "reason": reason,
            },
        )
        for listener in self._listeners:
            listener(event)
        return event

    def force_retire(self, reason: str = "emergency kill-switch") -> LifecycleEvent:
        """Escape hatch: allowed from any non-RETIRED state, bypassing the normal graph."""
        with self._lock:
            if self._state == LifecycleState.RETIRED:
                raise IllegalLifecycleTransition(self._state, LifecycleState.RETIRED)
            event = LifecycleEvent(previous=self._state, current=LifecycleState.RETIRED, reason=reason)
            self._state = LifecycleState.RETIRED
            self._history.append(event)
        logger.warning("lifecycle_force_retire", extra={"transition_id": event.transition_id, "reason": reason})
        for listener in self._listeners:
            listener(event)
        return event

    def is_operational(self) -> bool:
        return self._state in (LifecycleState.ACTIVE, LifecycleState.DEGRADED)
