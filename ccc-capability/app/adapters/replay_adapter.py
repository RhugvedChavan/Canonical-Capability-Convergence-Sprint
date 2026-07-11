from __future__ import annotations
from typing import Any, Callable
from app.adapters.base import CapabilityAdapterBase
from app.capability.events import CapabilityEvent


class ReplayAdapter(CapabilityAdapterBase):
    name = "replay"

    def __init__(self):
        super().__init__()
        self._log: list[CapabilityEvent] = []

    def _process(self, event: CapabilityEvent) -> dict[str, Any]:
        self._log.append(event)
        return {"status": "appended", "position": len(self._log) - 1}

    def replay(
        self,
        from_position: int = 0,
        to_position: int | None = None,
        sink: Callable[[CapabilityEvent], None] | None = None,
    ) -> list[dict]:
        """Re-emit a slice of the log, in original order, to an optional
        sink callback. Returns the structured metadata of every replayed
        event regardless of whether a sink was supplied."""
        window = self._log[from_position:to_position]
        for event in window:
            if sink:
                sink(event)
        return [e.to_execution_metadata() for e in window]

    def log_length(self) -> int:
        return len(self._log)

    def events_by_type(self, event_type: str) -> list[dict]:
        return [e.to_execution_metadata() for e in self._log if e.event_type.value == event_type]
