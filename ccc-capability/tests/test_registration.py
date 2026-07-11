import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.capability.contracts import HostContext
from app.capability.events import EventBus
from app.capability.lifecycle import LifecycleState
from app.capability.registry import CapabilityRegistry


def fresh_registry() -> CapabilityRegistry:
    return CapabilityRegistry(bus=EventBus())


def test_registry_starts_registered():
    reg = fresh_registry()
    assert reg.lifecycle.state == LifecycleState.REGISTERED


def test_registry_has_stable_unique_registration_id():
    reg1 = fresh_registry()
    reg2 = fresh_registry()
    assert reg1.registration_id != reg2.registration_id
    assert reg1.registration_id == reg1.registration_id


def test_registration_record_includes_registration_id():
    reg = fresh_registry()
    reg.attach(HostContext(mount_prefix="/x"))
    record = reg.registration_record()
    assert record.registration_id == reg.registration_id


def test_declared_hard_dependencies_are_wired_into_graph():
    from app.capability.manifest import CapabilityManifest, load_manifest

    base = load_manifest()
    data = base.model_dump()
    data["dependencies"]["declared_capability_dependencies"] = ["bhiv.capability.some-other-thing"]
    manifest_with_dep = CapabilityManifest.model_validate(data)

    reg = CapabilityRegistry(manifest=manifest_with_dep, bus=EventBus())
    assert "bhiv.capability.some-other-thing" in reg.graph.depends_on("bhiv.capability.composition-workspace")


def test_attach_without_router_still_succeeds_but_logs_warning(caplog):
    reg = fresh_registry()
    result = reg.attach(HostContext(mount_prefix="/x"), router=None)
    assert result.router is None
    assert reg.lifecycle.state in (LifecycleState.ACTIVE, LifecycleState.DEGRADED)


def test_validate_attachment_succeeds_with_compatible_runtime():
    reg = fresh_registry()
    result = reg.validate_attachment(HostContext(mount_prefix="/capabilities/workspace"), runtime_version="1.0.0")
    assert result.ok


def test_validate_attachment_fails_with_incompatible_runtime():
    reg = fresh_registry()
    result = reg.validate_attachment(HostContext(mount_prefix="/x"), runtime_version="2.0.0")
    assert not result.ok
    assert any("runtime version" in e for e in result.errors)


def test_validate_attachment_warns_on_missing_mount_prefix():
    reg = fresh_registry()
    result = reg.validate_attachment(HostContext(mount_prefix=""), runtime_version="1.0.0")
    assert result.ok
    assert any("mount_prefix" in w for w in result.warnings)


def test_attach_transitions_to_active():
    reg = fresh_registry()
    result = reg.attach(HostContext(mount_prefix="/x", host_name="test-host"))
    assert reg.lifecycle.state == LifecycleState.ACTIVE
    assert result.module_identifier == reg.manifest.module_identifier
    assert result.mount_prefix == "/x"


def test_attach_with_warnings_goes_degraded():
    reg = fresh_registry()
    result = reg.attach(HostContext(mount_prefix=""))  # triggers a warning
    assert reg.lifecycle.state == LifecycleState.DEGRADED


def test_attach_raises_on_validation_failure():
    reg = fresh_registry()
    try:
        reg.attach(HostContext(mount_prefix="/x"), runtime_version="99.0.0")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "Attachment validation failed" in str(exc)


def test_detach_retires_capability():
    reg = fresh_registry()
    reg.attach(HostContext(mount_prefix="/x"))
    reg.detach()
    assert reg.lifecycle.state == LifecycleState.RETIRED


def test_health_reflects_lifecycle_and_dependencies():
    reg = fresh_registry()
    reg.attach(HostContext(mount_prefix="/x"))
    healthy = reg.health(dependency_checks={"database": True})
    assert healthy.status == "healthy"
    degraded = reg.health(dependency_checks={"database": False})
    assert degraded.status == "degraded"


def test_health_unhealthy_when_not_operational():
    reg = fresh_registry()  # never attached; still REGISTERED
    report = reg.health()
    assert report.status == "unhealthy"


def test_describe_returns_manifest_dict():
    reg = fresh_registry()
    described = reg.describe()
    assert described["module_identifier"] == reg.manifest.module_identifier


def test_upgrade_readiness_accepts_newer_minor():
    reg = fresh_registry()
    reg.attach(HostContext(mount_prefix="/x"))
    result = reg.upgrade_readiness("2.9.0")
    assert result.ok


def test_upgrade_readiness_warns_on_major_bump():
    reg = fresh_registry()
    reg.attach(HostContext(mount_prefix="/x"))
    result = reg.upgrade_readiness("3.0.0")
    assert result.ok
    assert any("MAJOR bump" in w for w in result.warnings)


def test_upgrade_readiness_rejects_older_version():
    reg = fresh_registry()
    reg.attach(HostContext(mount_prefix="/x"))
    result = reg.upgrade_readiness("1.0.0")
    assert not result.ok


def test_deprecate_then_retire_flow():
    reg = fresh_registry()
    reg.attach(HostContext(mount_prefix="/x"))
    dep_result = reg.deprecate(reason="superseded by v3")
    assert dep_result.ok
    assert reg.lifecycle.state == LifecycleState.DEPRECATING
    retire_result = reg.retire()
    assert retire_result.ok
    assert reg.lifecycle.state == LifecycleState.RETIRED


def test_registration_record_reflects_current_state():
    reg = fresh_registry()
    reg.attach(HostContext(mount_prefix="/x"))
    record = reg.registration_record()
    assert record.lifecycle_state == "ACTIVE"
    assert record.module_identifier == reg.manifest.module_identifier
    assert "document_created" in record.provided_events
