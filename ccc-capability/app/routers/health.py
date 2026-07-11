from __future__ import annotations
from fastapi import APIRouter

from app.capability.registry import capability_registry
from app.database import check_connection

router = APIRouter(prefix="/capability", tags=["capability"])


@router.get("/health")
def health():
    db_ok = check_connection()
    adapter_checks = {a.name: a.is_healthy() for a in capability_registry.bus.adapters}
    checks = {"database": db_ok, **adapter_checks}
    report = capability_registry.health(dependency_checks=checks)
    return {
        "status": report.status,
        "lifecycle_state": report.lifecycle_state,
        "checks": report.checks,
        "checked_at": report.checked_at,
    }


@router.get("/manifest")
def manifest():
    return capability_registry.describe()


@router.get("/lifecycle")
def lifecycle():
    return {
        "current_state": capability_registry.lifecycle.state.value,
        "history": capability_registry.lifecycle.history,
        "registration_record": capability_registry.registration_record().__dict__,
    }


@router.get("/insights")
def insights():
    """Convenience read-only view of what the InsightFlow mock adapter has
    aggregated so far — useful for demoing the event pipeline end-to-end."""
    for adapter in capability_registry.bus.adapters:
        if adapter.name == "insightflow":
            return adapter.snapshot()
    return {"detail": "insightflow adapter not attached"}
