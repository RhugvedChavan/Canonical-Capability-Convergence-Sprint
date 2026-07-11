from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from app.capability.events import CapabilityEvent

logger = logging.getLogger("capability.adapters")


class CapabilityAdapterBase(ABC):
    name: str = "unnamed-adapter"

    def __init__(self):
        self.received_event_ids: set[str] = set()
        self.call_count: int = 0

    def handle_event(self, event: CapabilityEvent) -> dict[str, Any]:
        self.call_count += 1
        if event.event_id in self.received_event_ids:
            logger.info(
                "duplicate_event_ignored",
                extra={"adapter": self.name, "event_id": event.event_id},
            )
            return {"status": "duplicate_ignored", "event_id": event.event_id}
        self.received_event_ids.add(event.event_id)
        return self._process(event)

    def is_healthy(self) -> bool:

        return True

    @abstractmethod
    def _process(self, event: CapabilityEvent) -> dict[str, Any]:
        ...
