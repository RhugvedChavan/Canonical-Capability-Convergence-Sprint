import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.capability.authority import AuthorityGuard, AuthorityViolation
from app.capability.contracts import HostContext
from app.capability.events import EventBus
from app.capability.manifest import AuthorityBoundary
from app.capability.registry import CapabilityRegistry
from app.database import get_session
from app.exceptions import CapabilityError, DependencyUnavailableError, NotFoundError, register_exception_handlers
from app.main import app as real_app


# ---------- Authority boundary enforcement ----------
def test_authority_guard_permits_owned_resource():
    boundary = AuthorityBoundary(owns=["document", "task"], reads_but_does_not_own=[], will_not=[])
    guard = AuthorityGuard(boundary)
    guard.assert_owns("document")  # should not raise


def test_authority_guard_blocks_unowned_resource():
    boundary = AuthorityBoundary(owns=["document"], reads_but_does_not_own=[], will_not=[])
    guard = AuthorityGuard(boundary)
    with pytest.raises(AuthorityViolation):
        guard.assert_owns("user_credentials")


def test_authority_guard_blocks_declared_forbidden_action():
    boundary = AuthorityBoundary(
        owns=["document"], reads_but_does_not_own=[], will_not=["perform authentication decisions"]
    )
    guard = AuthorityGuard(boundary)
    with pytest.raises(AuthorityViolation):
        guard.assert_action_permitted("attempt to perform authentication decisions for user X")


# ---------- Attachment failure ----------
def test_attach_fails_with_clear_error_on_incompatible_runtime():
    reg = CapabilityRegistry(bus=EventBus())
    with pytest.raises(ValueError) as exc_info:
        reg.attach(HostContext(mount_prefix="/x"), runtime_version="99.9.9")
    assert "Attachment validation failed" in str(exc_info.value)


def test_attach_fails_when_already_retired():
    reg = CapabilityRegistry(bus=EventBus())
    reg.attach(HostContext(mount_prefix="/x"))
    reg.detach()
    with pytest.raises(ValueError):
        reg.attach(HostContext(mount_prefix="/x"))


# ---------- Exception handler behavior ----------
def _build_minimal_app() -> FastAPI:
    test_app = FastAPI()
    register_exception_handlers(test_app)

    @test_app.get("/boom-known")
    def boom_known():
        raise NotFoundError("thing not found", detail={"id": 123})

    @test_app.get("/boom-unknown")
    def boom_unknown():
        raise RuntimeError("totally unexpected")

    return test_app


def test_known_capability_error_returns_structured_json():
    client = TestClient(_build_minimal_app(), raise_server_exceptions=False)
    res = client.get("/boom-known")
    assert res.status_code == 404
    body = res.json()
    assert body["error"]["type"] == "NotFoundError"
    assert body["error"]["detail"]["id"] == 123


def test_unexpected_exception_returns_500_without_leaking_traceback():
    client = TestClient(_build_minimal_app(), raise_server_exceptions=False)
    res = client.get("/boom-unknown")
    assert res.status_code == 500
    body = res.json()
    assert body["error"]["type"] == "InternalServerError"
    assert "boom" not in body["error"]["message"]  # no raw exception text leaked


def test_dependency_unavailable_error_has_503_status():
    err = DependencyUnavailableError("database down")
    assert err.status_code == 503
    assert isinstance(err, CapabilityError)


# ---------- Malformed request handling on the real app ----------
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

    real_app.dependency_overrides[get_session] = override
    client = TestClient(real_app)
    yield client
    real_app.dependency_overrides.clear()


def test_missing_document_returns_404(client):
    res = client.get("/documents/999999")
    assert res.status_code == 404


def test_missing_document_error_body_is_structured_not_bare_detail(client):
    """Regression test: crud.py's existing HTTPException(404) usage is
    correct and untouched, but the response body must now go through the
    same centralized {"error": {...}} shape as CapabilityError, instead of
    FastAPI's default bare {"detail": "..."}."""
    res = client.get("/documents/999999")
    body = res.json()
    assert "error" in body
    assert body["error"]["type"] == "HTTPException"
    assert "not found" in body["error"]["message"]


def test_malformed_task_payload_returns_422(client):
    res = client.post("/tasks", json={"description": "no title supplied"})
    assert res.status_code == 422


def test_validation_error_body_is_structured(client):
    res = client.post("/tasks", json={"description": "no title supplied"})
    body = res.json()
    assert body["error"]["type"] == "RequestValidationError"
    assert "errors" in body["error"]["detail"]


def test_invalid_status_value_returns_422(client):
    res = client.get("/documents?status=not_a_real_status")
    assert res.status_code == 422
