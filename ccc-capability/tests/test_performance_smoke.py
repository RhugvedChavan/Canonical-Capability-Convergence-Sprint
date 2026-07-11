import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.database import get_session
from app.main import app


@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(name="client")
def client_fixture(session):
    def override():
        return session

    app.dependency_overrides[get_session] = override
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def test_creating_50_documents_completes_quickly(client):
    start = time.perf_counter()
    for i in range(50):
        res = client.post("/documents", json={"title": f"Doc {i}", "content": "x" * 100})
        assert res.status_code == 201
    elapsed = time.perf_counter() - start
    assert elapsed < 5.0, f"Creating 50 documents took {elapsed:.2f}s, expected < 5s"


def test_creating_50_tasks_completes_quickly(client):
    start = time.perf_counter()
    for i in range(50):
        res = client.post("/tasks", json={"title": f"Task {i}"})
        assert res.status_code == 201
    elapsed = time.perf_counter() - start
    assert elapsed < 5.0, f"Creating 50 tasks took {elapsed:.2f}s, expected < 5s"


def test_dashboard_summary_stays_fast_with_moderate_data(client):
    for i in range(30):
        client.post("/documents", json={"title": f"Doc {i}"})
        client.post("/tasks", json={"title": f"Task {i}"})

    start = time.perf_counter()
    res = client.get("/dashboard/summary")
    elapsed = time.perf_counter() - start
    assert res.status_code == 200
    assert elapsed < 1.0, f"Dashboard summary took {elapsed:.2f}s, expected < 1s"


def test_document_list_with_search_stays_fast(client):
    for i in range(50):
        client.post("/documents", json={"title": f"Chapter {i}"})

    start = time.perf_counter()
    res = client.get("/documents?search=chapter")
    elapsed = time.perf_counter() - start
    assert res.status_code == 200
    assert len(res.json()) == 50
    assert elapsed < 1.0, f"Search query took {elapsed:.2f}s, expected < 1s"


def test_event_bus_dispatch_overhead_is_negligible():
    """Emitting an event to zero adapters (the common case in an isolated
    test DB) should be effectively free — this guards against someone
    accidentally adding blocking I/O to the hot dispatch path."""
    from app.capability.events import EventBus, EventType

    bus = EventBus()
    start = time.perf_counter()
    for i in range(200):
        bus.emit(
            EventType.DOCUMENT_CREATED, entity_type="document", entity_id=i, actor_id=1, payload={"i": i},
        )
    elapsed = time.perf_counter() - start
    assert elapsed < 1.0, f"200 zero-adapter dispatches took {elapsed:.2f}s, expected < 1s"
