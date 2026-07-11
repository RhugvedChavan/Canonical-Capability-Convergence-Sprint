import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from app.capability.manifest import CapabilityManifest, load_manifest


def test_manifest_loads_without_error():
    manifest = load_manifest()
    assert isinstance(manifest, CapabilityManifest)


def test_manifest_has_module_identifier():
    manifest = load_manifest()
    assert manifest.module_identifier == "bhiv.capability.composition-workspace"


def test_manifest_has_semver_version():
    manifest = load_manifest()
    parts = manifest.capability_version.split(".")
    assert len(parts) == 3
    assert all(p.isdigit() for p in parts)


def test_manifest_declares_lifecycle_states():
    manifest = load_manifest()
    expected = {
        "UNREGISTERED", "REGISTERED", "INITIALIZING",
        "ACTIVE", "DEGRADED", "DEPRECATING", "RETIRED",
    }
    assert set(manifest.lifecycle.states) == expected


def test_manifest_declares_authority_boundary():
    manifest = load_manifest()
    assert "document" in manifest.authority_boundary.owns
    assert "task" in manifest.authority_boundary.owns
    assert len(manifest.authority_boundary.will_not) > 0


def test_manifest_declares_all_named_event_types():
    manifest = load_manifest()
    events = set(manifest.public_api_contract.event_stream["event_types"])
    required = {
        "document_created", "document_updated", "version_restored",
        "comment_added", "task_created", "task_updated",
        "task_completed", "document_deleted",
    }
    assert required.issubset(events)


def test_manifest_declares_five_bhiv_adapters():
    manifest = load_manifest()
    adapters = manifest.internal_extension_points.registered_adapters
    assert len(adapters) == 5
    for expected in ["bucket", "replay", "insightflow", "runtime_registry", "rajya"]:
        assert any(expected in a for a in adapters)


def test_missing_manifest_file_raises(tmp_path):
    fake_path = tmp_path / "does_not_exist.json"
    with pytest.raises(FileNotFoundError):
        load_manifest(path=fake_path)


def test_manifest_declares_capability_metadata():
    manifest = load_manifest()
    assert manifest.capability_metadata is not None
    assert manifest.capability_metadata.owner_team
    assert "bhiv-capability" in manifest.capability_metadata.tags


def test_manifest_event_types_include_document_uploaded():
    manifest = load_manifest()
    assert "document_uploaded" in manifest.public_api_contract.event_stream["event_types"]


def test_manifest_resources_include_insights_endpoint():
    manifest = load_manifest()
    paths = [r["path"] for r in manifest.public_api_contract.resources]
    assert "/capability/insights" in paths
