from __future__ import annotations

from collections import Counter, deque
from typing import Any

from app.adapters.base import CapabilityAdapterBase
from app.capability.events import CapabilityEvent


class InsightFlowAdapter(CapabilityAdapterBase):
    name = "insightflow"

    def __init__(self, rolling_window: int = 100):
        super().__init__()
        self.counts_by_event_type: Counter = Counter()
        self.counts_by_entity_type: Counter = Counter()
        self._recent: deque[str] = deque(maxlen=rolling_window)

    def _process(self, event: CapabilityEvent) -> dict[str, Any]:
        self.counts_by_event_type[event.event_type.value] += 1
        self.counts_by_entity_type[event.entity_type] += 1
        self._recent.append(event.occurred_at)
        return {
            "status": "aggregated",
            "total_events_seen": sum(self.counts_by_event_type.values()),
        }

    def snapshot(self) -> dict[str, Any]:
        return {
            "counts_by_event_type": dict(self.counts_by_event_type),
            "counts_by_entity_type": dict(self.counts_by_entity_type),
            "rolling_window_size": len(self._recent),
        }
