from __future__ import annotations

from typing import Any

from app.adapters.base import CapabilityAdapterBase
from app.capability.events import CapabilityEvent, EventType


class BucketAdapter(CapabilityAdapterBase):
    name = "bucket"

    RELEVANT_EVENTS = {
        EventType.DOCUMENT_CREATED,
        EventType.DOCUMENT_UPDATED,
        EventType.VERSION_RESTORED,
        EventType.DOCUMENT_UPLOADED,
    }

    def __init__(self):
        super().__init__()
        self._objects: dict[str, dict[str, Any]] = {}

    def _object_key(self, event: CapabilityEvent) -> str:
        return f"documents/{event.entity_id}/{event.event_id}.snapshot"

    def _process(self, event: CapabilityEvent) -> dict[str, Any]:
        if event.event_type not in self.RELEVANT_EVENTS:
            return {"status": "ignored", "reason": "not a storage-relevant event"}

        key = self._object_key(event)
        content = event.payload.get("content", "")
        self._objects[key] = {
            "key": key,
            "size_bytes": len(content.encode("utf-8")),
            "event_id": event.event_id,
            "stored_at": event.occurred_at,
        }
        return {"status": "stored", "object_key": key, "size_bytes": self._objects[key]["size_bytes"]}

    def get_object(self, key: str) -> dict[str, Any] | None:
        return self._objects.get(key)

    def list_objects(self) -> list[str]:
        return sorted(self._objects.keys())
