import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.capability.events import event_bus
from app.database import get_session
from app.main import app


@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(name="client")
def client_fixture(session: Session):
    def get_session_override():
        return session

    app.dependency_overrides[get_session] = get_session_override
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


class RecordingAdapter:
    """A minimal adapter used only to observe what the bus dispatches."""

    def __init__(self, name: str):
        self.name = name
        self.received: list = []

    def handle_event(self, event):
        self.received.append(event)
        return {"status": "recorded"}


@pytest.fixture(name="recorder")
def recorder_fixture():
    adapter = RecordingAdapter(name="test-recorder")
    event_bus.register_adapter(adapter)
    yield adapter
    event_bus.unregister_adapter("test-recorder")


def test_document_creation_emits_document_created_event(client, recorder):
    res = client.post("/documents", json={"title": "Chapter One", "content": "text"})
    assert res.status_code == 201
    types = [e.event_type.value for e in recorder.received]
    assert "document_created" in types


def test_document_update_emits_document_updated_event(client, recorder):
    doc = client.post("/documents", json={"title": "A", "content": "v1"}).json()
    recorder.received.clear()
    client.put(f"/documents/{doc['id']}", json={"content": "v2"})
    types = [e.event_type.value for e in recorder.received]
    assert "document_updated" in types


def test_version_restore_emits_version_restored_event(client, recorder):
    doc = client.post("/documents", json={"title": "A", "content": "original"}).json()
    client.put(f"/documents/{doc['id']}", json={"content": "changed"})
    recorder.received.clear()
    client.post(f"/documents/{doc['id']}/versions/1/restore")
    types = [e.event_type.value for e in recorder.received]
    assert "version_restored" in types


def test_comment_added_emits_event(client, recorder):
    doc = client.post("/documents", json={"title": "A"}).json()
    recorder.received.clear()
    client.post(f"/documents/{doc['id']}/comments", json={"text": "nice line"})
    types = [e.event_type.value for e in recorder.received]
    assert "comment_added" in types


def test_document_delete_emits_event(client, recorder):
    doc = client.post("/documents", json={"title": "A"}).json()
    recorder.received.clear()
    client.delete(f"/documents/{doc['id']}")
    types = [e.event_type.value for e in recorder.received]
    assert "document_deleted" in types


def test_task_created_emits_event(client, recorder):
    recorder.received.clear()
    client.post("/tasks", json={"title": "Review intro"})
    types = [e.event_type.value for e in recorder.received]
    assert "task_created" in types


def test_task_completed_emits_task_completed_not_task_updated(client, recorder):
    task = client.post("/tasks", json={"title": "T1"}).json()
    recorder.received.clear()
    client.patch(f"/tasks/{task['id']}", json={"status": "done"})
    types = [e.event_type.value for e in recorder.received]
    assert "task_completed" in types
    assert "task_updated" not in types


def test_task_status_change_to_non_done_emits_task_updated(client, recorder):
    task = client.post("/tasks", json={"title": "T1"}).json()
    recorder.received.clear()
    client.patch(f"/tasks/{task['id']}", json={"status": "in_progress"})
    types = [e.event_type.value for e in recorder.received]
    assert "task_updated" in types


def test_emitted_event_has_structured_execution_metadata(client, recorder):
    client.post("/documents", json={"title": "Meta Test"})
    event = recorder.received[-1]
    metadata = event.to_execution_metadata()
    for key in ["event_id", "event_type", "occurred_at", "entity_type", "module_identifier", "schema_version"]:
        assert key in metadata


def test_events_carry_stable_unique_ids(client, recorder):
    client.post("/documents", json={"title": "A"})
    client.post("/documents", json={"title": "B"})
    ids = [e.event_id for e in recorder.received]
    assert len(ids) == len(set(ids))  # all unique


def test_events_carry_monotonically_increasing_sequence(client, recorder):
    client.post("/documents", json={"title": "A"})
    client.post("/documents", json={"title": "B"})
    client.post("/documents", json={"title": "C"})
    sequences = [e.sequence for e in recorder.received]
    assert sequences == sorted(sequences)
    assert len(set(sequences)) == len(sequences)


def test_event_module_identifier_matches_manifest(client, recorder):
    from app.capability.manifest import load_manifest

    client.post("/documents", json={"title": "A"})
    event = recorder.received[-1]
    assert event.module_identifier == load_manifest().module_identifier
    assert event.capability_version == load_manifest().capability_version
