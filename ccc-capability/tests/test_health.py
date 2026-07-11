import os
import sys

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
    # Bare TestClient (no `with`) intentionally does NOT trigger lifespan,
    # matching the rest of this suite — health/manifest/lifecycle read from
    # the capability_registry singleton's current in-process state
    # regardless of whether this particular process ran startup, since the
    # registry is constructed (and transitions to REGISTERED) at import time.
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def test_health_endpoint_returns_200(client):
    res = client.get("/capability/health")
    assert res.status_code == 200
    body = res.json()
    assert "status" in body
    assert "lifecycle_state" in body
    assert "checks" in body
    assert "database" in body["checks"]


def test_health_endpoint_reports_database_check_true_with_valid_session(client):
    res = client.get("/capability/health")
    body = res.json()
    assert body["checks"]["database"] is True


def test_manifest_endpoint_returns_full_manifest(client):
    res = client.get("/capability/manifest")
    assert res.status_code == 200
    body = res.json()
    assert body["module_identifier"] == "bhiv.capability.composition-workspace"
    assert "authority_boundary" in body
    assert "lifecycle" in body


def test_lifecycle_endpoint_returns_current_state_and_history(client):
    res = client.get("/capability/lifecycle")
    assert res.status_code == 200
    body = res.json()
    assert "current_state" in body
    assert "history" in body
    assert "registration_record" in body
    assert isinstance(body["history"], list)


def test_insights_endpoint_returns_something_sensible(client):
    res = client.get("/capability/insights")
    assert res.status_code == 200
    body = res.json()
    # Either a real snapshot (if insightflow adapter is attached) or a
    # graceful "not attached" message — never a 500.
    assert isinstance(body, dict)


def test_health_status_field_is_one_of_known_values(client):
    res = client.get("/capability/health")
    body = res.json()
    assert body["status"] in {"healthy", "degraded", "unhealthy"}


def test_health_reflects_real_adapter_health_not_hardcoded(client):
    """Regression test: /capability/health must call each adapter's own
    is_healthy(), not assume every attached adapter is trivially healthy."""
    from app.capability.events import event_bus

    class FlakyAdapter:
        name = "flaky-test-adapter"

        def handle_event(self, event):
            return {"status": "ok"}

        def is_healthy(self):
            return False

    adapter = FlakyAdapter()
    event_bus.register_adapter(adapter)
    try:
        res = client.get("/capability/health")
        body = res.json()
        assert body["checks"]["flaky-test-adapter"] is False
        assert body["status"] != "healthy"
    finally:
        event_bus.unregister_adapter("flaky-test-adapter")
