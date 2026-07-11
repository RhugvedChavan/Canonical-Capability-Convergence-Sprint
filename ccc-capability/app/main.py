from __future__ import annotations
import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.staticfiles import StaticFiles

from app.adapters.bucket_adapter import BucketAdapter
from app.adapters.insightflow_adapter import InsightFlowAdapter
from app.adapters.rajya_adapter import RajyaAdapter
from app.adapters.replay_adapter import ReplayAdapter
from app.adapters.runtime_registry_adapter import RuntimeRegistryAdapter
from app.capability.contracts import HostContext
from app.capability.registry import capability_registry
from app.config import get_settings
from app.database import check_connection, init_db
from app.exceptions import DependencyUnavailableError, register_exception_handlers
from app.logging_config import configure_logging
from app.routers import coordination, dashboard, documents, health, users

settings = get_settings()
configure_logging(
    level=settings.log_level,
    fmt=settings.log_format,
    service_name=settings.service_name,
    environment=settings.environment,
)
logger = logging.getLogger("capability.startup")

capability_router = APIRouter()
capability_router.include_router(users.router)
capability_router.include_router(documents.router)
capability_router.include_router(coordination.router)
capability_router.include_router(dashboard.router)
capability_router.include_router(health.router)


def _build_adapters() -> list:
    adapters = []
    if settings.enable_bucket_adapter:
        adapters.append(BucketAdapter())
    if settings.enable_replay_adapter:
        adapters.append(ReplayAdapter())
    if settings.enable_insightflow_adapter:
        adapters.append(InsightFlowAdapter())
    if settings.enable_runtime_registry_adapter:
        rr = RuntimeRegistryAdapter(
            module_identifier=capability_registry.manifest.module_identifier,
            capability_version=capability_registry.manifest.capability_version,
        )
        rr.register()
        adapters.append(rr)
    if settings.enable_rajya_adapter:
        adapters.append(RajyaAdapter())
    return adapters


def run_startup_validation() -> None:
    """Deterministic startup validation: fail fast (per config) if a
    required dependency isn't reachable, or if the capability's own
    dependency graph is invalid, rather than serving traffic in a silently
    broken state."""
    dep_result = capability_registry.validate_dependencies()
    if not dep_result.ok:
        message = f"Capability dependency graph is invalid: {dep_result.errors}"
        logger.error("startup_validation_failed", extra={"reason": message})
        if settings.fail_fast_on_startup_errors:
            raise DependencyUnavailableError(message)

    if not check_connection():
        message = "Database is not reachable at startup"
        logger.error("startup_validation_failed", extra={"reason": message})
        if settings.fail_fast_on_startup_errors:
            raise DependencyUnavailableError(message)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    run_startup_validation()

    for adapter in _build_adapters():
        capability_registry.bus.register_adapter(adapter)

    host_context = HostContext(
        mount_prefix=settings.mount_prefix,
        host_name=settings.host_name,
    )
    result = capability_registry.attach(
        host_context, router=capability_router, runtime_version=settings.tantra_runtime_version
    )
    logger.info(
        "capability_ready",
        extra={
            "module_identifier": result.module_identifier,
            "capability_version": result.capability_version,
            "lifecycle_state": capability_registry.lifecycle.state.value,
        },
    )
    yield
    capability_registry.detach()


app = FastAPI(
    title=capability_registry.manifest.capability_name,
    description=capability_registry.manifest.summary,
    version=capability_registry.manifest.capability_version,
    lifespan=lifespan,
)

register_exception_handlers(app)
app.include_router(capability_router)
app.mount("/", StaticFiles(directory="static", html=True), name="static")
