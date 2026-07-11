from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Optional

from app.adapters.base import CapabilityAdapterBase
from app.capability.events import CapabilityEvent


class RuntimeRegistryAdapter(CapabilityAdapterBase):
    name = "runtime-registry"

    def __init__(self, module_identifier: str, capability_version: str):
        super().__init__()
        self.module_identifier = module_identifier
        self.capability_version = capability_version
        self._registered = False
        self._last_heartbeat: Optional[str] = None
        self._event_count = 0

    def register(self) -> dict[str, Any]:
        self._registered = True
        self._last_heartbeat = datetime.now(timezone.utc).isoformat()
        return {
            "status": "registered",
            "module_identifier": self.module_identifier,
            "capability_version": self.capability_version,
        }

    def is_healthy(self) -> bool:
        """Unlike the default (always-True) base behavior, this adapter has
        a real, meaningful health signal: it isn't healthy until it has
        actually completed registration with the runtime registry."""
        return self._registered

    def _process(self, event: CapabilityEvent) -> dict[str, Any]:
        self._event_count += 1
        self._last_heartbeat = event.occurred_at
        return {"status": "heartbeat_recorded", "event_count": self._event_count}

    def is_healthy(self) -> bool:
        """Concrete health signal: this adapter is only meaningfully
        healthy once register() has actually completed — a Runtime
        Registry adapter that never registered can't be trusted to have
        told the registry this capability exists."""
        return self._registered

    def status(self) -> dict[str, Any]:
        return {
            "registered": self._registered,
            "last_heartbeat": self._last_heartbeat,
            "event_count": self._event_count,
        }

    def is_healthy(self) -> bool:
        """A runtime registry adapter that hasn't completed registration
        yet cannot be trusted to reflect this capability's presence
        accurately — report unhealthy until register() has run."""
        return self._registered
