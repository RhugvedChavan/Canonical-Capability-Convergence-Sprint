from __future__ import annotations
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

MANIFEST_PATH = Path(__file__).resolve().parents[2] / "capability.manifest.json"


class AuthorityBoundary(BaseModel):
    owns: list[str] = Field(default_factory=list)
    reads_but_does_not_own: list[str] = Field(default_factory=list)
    will_not: list[str] = Field(default_factory=list)
    escalation_contact: Optional[str] = None


class CapabilityMetadata(BaseModel):
    """Supplementary descriptive metadata beyond the core identity fields
    (module_identifier, capability_name, capability_version, summary) that
    already live directly on CapabilityManifest. Optional so manifests
    written before this field existed still validate."""

    owner_team: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    created_at: Optional[str] = None
    documentation: list[str] = Field(default_factory=list)


class LifecycleDeclaration(BaseModel):
    states: list[str]
    current_state: str
    deterministic_transitions: dict[str, str]


class CapabilityAttachmentInterface(BaseModel):
    entrypoint: str
    attach_method: str
    detach_method: str
    health_method: str
    describe_method: str


class PublicApiContract(BaseModel):
    transport: str
    router_entrypoint: str
    resources: list[dict[str, Any]]
    event_stream: dict[str, Any]


class InternalExtensionPoints(BaseModel):
    adapter_protocol: str
    registered_adapters: list[str]
    extension_hooks: list[str]
    identity_delegation_hook: str


class CapabilityRegistrationStructure(BaseModel):
    registry_entrypoint: str
    registration_fields: list[str]


class Dependencies(BaseModel):
    runtime: list[dict[str, str]]
    declared_capability_dependencies: list[str] = Field(default_factory=list)
    declared_capability_optional_peers: list[str] = Field(default_factory=list)


class Compatibility(BaseModel):
    tantra_runtime_min_version: str
    tantra_runtime_max_tested_version: str
    semver_policy: str


class CapabilityManifest(BaseModel):
    module_identifier: str
    capability_name: str
    capability_version: str
    manifest_version: str
    summary: str
    capability_metadata: Optional[CapabilityMetadata] = None
    authority_boundary: AuthorityBoundary
    lifecycle: LifecycleDeclaration
    capability_attachment_interface: CapabilityAttachmentInterface
    public_api_contract: PublicApiContract
    internal_extension_points: InternalExtensionPoints
    capability_registration_structure: CapabilityRegistrationStructure
    dependencies: Dependencies
    compatibility: Compatibility
    maintainers: list[str] = Field(default_factory=list)
    license: Optional[str] = None


@lru_cache(maxsize=1)
def load_manifest(path: Optional[Path] = None) -> CapabilityManifest:
    """Load and validate capability.manifest.json. Cached after first read."""
    manifest_path = path or MANIFEST_PATH
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Capability manifest not found at {manifest_path}. "
            "A capability cannot register without a manifest."
        )
    raw = json.loads(manifest_path.read_text())
    return CapabilityManifest.model_validate(raw)
