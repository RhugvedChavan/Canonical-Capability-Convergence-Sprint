from __future__ import annotations
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter

from app.capability.authority import AuthorityGuard
from app.capability.compatibility import CompatibilityMatrix, SemVer, satisfies_range
from app.capability.contracts import AttachmentResult, HealthReport, HostContext
from app.capability.dependency_graph import DependencyCycleError, DependencyGraph
from app.capability.events import EventBus, event_bus
from app.capability.lifecycle import IllegalLifecycleTransition, LifecycleManager, LifecycleState
from app.capability.manifest import CapabilityManifest, load_manifest

logger = logging.getLogger("capability.registry")

SELF_NODE = "bhiv.capability.composition-workspace"


@dataclass
class RegistrationRecord:
    registration_id: str
    module_identifier: str
    capability_version: str
    declared_dependencies: list[str]
    provided_events: list[str]
    lifecycle_state: str
    health_endpoint: str
    attached_at: Optional[str] = None


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class CapabilityRegistry:
    """Concrete implementation of the CapabilityContract protocol."""

    def __init__(self, manifest: Optional[CapabilityManifest] = None, bus: Optional[EventBus] = None):
        self.manifest: CapabilityManifest = manifest or load_manifest()
        self.lifecycle = LifecycleManager()
        self.graph = DependencyGraph()
        self.compatibility = CompatibilityMatrix()
        self.authority = AuthorityGuard(self.manifest.authority_boundary)
        self.bus = bus or event_bus
        self.registration_id: str = str(uuid.uuid4())
        self._router: Optional[APIRouter] = None
        self._host_context: Optional[HostContext] = None
        self._attached_at: Optional[str] = None

        self.graph.add_node(SELF_NODE)
        for dep in self.manifest.dependencies.declared_capability_dependencies:
            self.graph.add_dependency(SELF_NODE, dep)
        for peer in self.manifest.dependencies.declared_capability_optional_peers:
            self.graph.add_node(peer)

        self.compatibility.declare(
            "tantra-runtime",
            self.manifest.compatibility.tantra_runtime_min_version,
            self.manifest.compatibility.tantra_runtime_max_tested_version,
            required=True,
        )
        for peer in self.manifest.dependencies.declared_capability_optional_peers:
            self.compatibility.declare(peer, "0.1.0", None, required=False)

        self.lifecycle.transition_to(LifecycleState.REGISTERED, reason="registry constructed")

    # ---------- Dependency & Attachment Validation ----------

    def validate_dependencies(self) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []
        try:
            self.graph.validate(allow_unknown=True)
        except DependencyCycleError as exc:
            errors.append(str(exc))
        return ValidationResult(ok=not errors, errors=errors, warnings=warnings)

    def validate_attachment(self, host_context: HostContext, runtime_version: str = "1.0.0") -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []

        dep_result = self.validate_dependencies()
        errors.extend(dep_result.errors)

        if not satisfies_range(
            runtime_version,
            self.manifest.compatibility.tantra_runtime_min_version,
            self.manifest.compatibility.tantra_runtime_max_tested_version,
        ):
            errors.append(
                f"TANTRA runtime version {runtime_version} is outside supported range "
                f"[{self.manifest.compatibility.tantra_runtime_min_version}, "
                f"{self.manifest.compatibility.tantra_runtime_max_tested_version}]"
            )

        if self.lifecycle.state not in (LifecycleState.REGISTERED, LifecycleState.INITIALIZING):
            if self.lifecycle.state in (LifecycleState.RETIRED, LifecycleState.DEPRECATING):
                errors.append(f"Cannot attach a capability in state {self.lifecycle.state.value}")
            else:
                warnings.append(f"Attaching while already in state {self.lifecycle.state.value}")

        if not host_context.mount_prefix:
            warnings.append("No mount_prefix supplied; capability will mount at root")

        return ValidationResult(ok=not errors, errors=errors, warnings=warnings)

    # ---------- CapabilityContract implementation ----------

    def attach(
        self,
        host_context: HostContext,
        router: Optional[APIRouter] = None,
        runtime_version: str = "1.0.0",
    ) -> AttachmentResult:
        validation = self.validate_attachment(host_context, runtime_version=runtime_version)
        if not validation.ok:
            raise ValueError(f"Attachment validation failed: {validation.errors}")
        if router is None:
            logger.warning(
                "attach_called_without_router",
                extra={"host": host_context.host_name},
            )

        if self.lifecycle.state == LifecycleState.REGISTERED:
            self.lifecycle.transition_to(LifecycleState.INITIALIZING, reason="attach() called")

        self._host_context = host_context
        self._router = router
        self._attached_at = datetime.now(timezone.utc).isoformat()

        target = LifecycleState.DEGRADED if validation.warnings else LifecycleState.ACTIVE
        self.lifecycle.transition_to(target, reason="startup validation completed")

        logger.info(
            "capability_attached",
            extra={"host": host_context.host_name, "mount_prefix": host_context.mount_prefix},
        )

        return AttachmentResult(
            router=router,
            mount_prefix=host_context.mount_prefix,
            module_identifier=self.manifest.module_identifier,
            capability_version=self.manifest.capability_version,
            health_check_path=f"{host_context.mount_prefix}/capability/health",
        )

    def detach(self) -> None:
        if self.lifecycle.can_transition_to(LifecycleState.DEPRECATING):
            self.lifecycle.transition_to(LifecycleState.DEPRECATING, reason="detach() called")
        self.lifecycle.transition_to(LifecycleState.RETIRED, reason="detach completed")
        self._router = None
        self._host_context = None
        logger.info("capability_detached")

    def health(self, dependency_checks: Optional[dict] = None) -> HealthReport:
        dependency_checks = dependency_checks or {}
        all_ok = all(dependency_checks.values()) if dependency_checks else True
        if not self.lifecycle.is_operational():
            status = "unhealthy"
        elif not all_ok:
            status = "degraded"
        else:
            status = "healthy"
        return HealthReport(
            status=status,
            lifecycle_state=self.lifecycle.state.value,
            checks=dependency_checks,
            checked_at=datetime.now(timezone.utc).isoformat(),
        )

    def describe(self) -> dict:
        described = self.manifest.model_dump()
        described["lifecycle"]["current_state"] = self.lifecycle.state.value
        return described

    # ---------- Upgrade Readiness ----------

    def upgrade_readiness(self, target_version: str) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []
        try:
            current = SemVer.parse(self.manifest.capability_version)
            target = SemVer.parse(target_version)
        except Exception as exc:
            return ValidationResult(ok=False, errors=[str(exc)])

        if target <= current:
            errors.append(f"Target version {target} is not newer than current {current}")
        if target.major != current.major:
            warnings.append(
                f"Target version {target} is a MAJOR bump from {current}; "
                "public_api_contract may have breaking changes — review before upgrading"
            )
        if self.lifecycle.state not in (LifecycleState.ACTIVE, LifecycleState.DEGRADED):
            errors.append(f"Cannot assess upgrade readiness while in state {self.lifecycle.state.value}")

        return ValidationResult(ok=not errors, errors=errors, warnings=warnings)

    # ---------- Deprecation Handling ----------

    def deprecate(self, reason: str = "scheduled deprecation") -> ValidationResult:
        dependents = self.graph.dependents_of(SELF_NODE)
        warnings = []
        if dependents:
            warnings.append(
                f"{len(dependents)} node(s) depend on this capability and will be "
                f"affected by deprecation: {sorted(dependents)}"
            )
        try:
            self.lifecycle.transition_to(LifecycleState.DEPRECATING, reason=reason)
        except IllegalLifecycleTransition as exc:
            return ValidationResult(ok=False, errors=[str(exc)])
        return ValidationResult(ok=True, warnings=warnings)

    def retire(self, reason: str = "deprecation window elapsed") -> ValidationResult:
        try:
            self.lifecycle.transition_to(LifecycleState.RETIRED, reason=reason)
        except IllegalLifecycleTransition as exc:
            return ValidationResult(ok=False, errors=[str(exc)])
        return ValidationResult(ok=True)

    # ---------- Registration structure ----------

    def registration_record(self) -> RegistrationRecord:
        return RegistrationRecord(
            registration_id=self.registration_id,
            module_identifier=self.manifest.module_identifier,
            capability_version=self.manifest.capability_version,
            declared_dependencies=list(self.graph.depends_on(SELF_NODE)),
            provided_events=self.manifest.public_api_contract.event_stream["event_types"],
            lifecycle_state=self.lifecycle.state.value,
            health_endpoint="/capability/health",
            attached_at=self._attached_at,
        )


# Process-wide singleton registry, mirroring event_bus.
capability_registry = CapabilityRegistry()
