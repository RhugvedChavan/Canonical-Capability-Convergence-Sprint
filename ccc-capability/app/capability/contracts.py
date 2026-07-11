from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Optional, Protocol, runtime_checkable

from fastapi import APIRouter


@dataclass
class HostContext:
    """What the attaching host tells the capability about itself."""
    mount_prefix: str = ""
    host_name: str = "unknown-host"
    # Optional: host supplies real identity resolution instead of the
    # capability's local fallback user bootstrap.
    user_resolver: Optional[Callable[[str], Optional[int]]] = None
    extra: dict = field(default_factory=dict)


@dataclass
class AttachmentResult:
    """What the capability hands back to a host after a successful attach()."""
    router: APIRouter
    mount_prefix: str
    module_identifier: str
    capability_version: str
    health_check_path: str


@dataclass
class HealthReport:
    status: str  # "healthy" | "degraded" | "unhealthy"
    lifecycle_state: str
    checks: dict
    checked_at: str


@runtime_checkable
class UserResolver(Protocol):
    """Identity delegation hook. A host platform may supply its own resolver
    that maps an external identity token to an internal user id; if it
    doesn't, the capability falls back to its own local user bootstrap."""

    def resolve(self, external_identity: str) -> Optional[int]:
        ...


@runtime_checkable
class CapabilityContract(Protocol):
    """The interface every BHIV capability must implement to be attachable."""

    def attach(self, host_context: HostContext) -> AttachmentResult:
        ...

    def detach(self) -> None:
        ...

    def health(self) -> HealthReport:
        ...

    def describe(self) -> dict:
        ...
