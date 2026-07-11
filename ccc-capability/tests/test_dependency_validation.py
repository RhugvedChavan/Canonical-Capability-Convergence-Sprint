import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from app.capability.compatibility import (
    CompatibilityMatrix,
    InvalidVersionError,
    SemVer,
    satisfies_range,
)
from app.capability.dependency_graph import (
    DependencyCycleError,
    DependencyGraph,
    UnknownDependencyError,
)


# ---------- Dependency graph ----------
def test_graph_with_no_cycle_validates():
    g = DependencyGraph()
    g.add_dependency("workspace", "database")
    g.add_dependency("workspace", "bucket")
    g.validate()  # should not raise


def test_graph_detects_direct_cycle():
    g = DependencyGraph()
    g.add_dependency("a", "b")
    g.add_dependency("b", "a")
    with pytest.raises(DependencyCycleError):
        g.validate()


def test_graph_detects_indirect_cycle():
    g = DependencyGraph()
    g.add_dependency("a", "b")
    g.add_dependency("b", "c")
    g.add_dependency("c", "a")
    with pytest.raises(DependencyCycleError):
        g.validate()


def test_graph_unknown_dependency_detection():
    g = DependencyGraph()
    g.add_node("workspace")
    g.edges["workspace"].add("nonexistent")
    with pytest.raises(UnknownDependencyError):
        g.validate(allow_unknown=False)


def test_topological_order_respects_dependencies():
    g = DependencyGraph()
    g.add_dependency("workspace", "database")
    g.add_dependency("database", "disk")
    order = g.topological_order()
    assert order.index("disk") < order.index("database")
    assert order.index("database") < order.index("workspace")


def test_dependents_of_reverse_lookup():
    g = DependencyGraph()
    g.add_dependency("workspace", "database")
    g.add_dependency("dashboard", "database")
    assert g.dependents_of("database") == {"workspace", "dashboard"}


# ---------- SemVer ----------
def test_semver_parses_valid_version():
    v = SemVer.parse("2.0.0")
    assert (v.major, v.minor, v.patch) == (2, 0, 0)


def test_semver_rejects_invalid_version():
    with pytest.raises(InvalidVersionError):
        SemVer.parse("not-a-version")


def test_semver_ordering():
    assert SemVer.parse("1.2.0") < SemVer.parse("1.3.0")
    assert SemVer.parse("2.0.0") > SemVer.parse("1.99.99")


def test_semver_compatible_same_major():
    assert SemVer.parse("2.1.0").is_compatible_with(SemVer.parse("2.5.3"))


def test_semver_incompatible_different_major():
    assert not SemVer.parse("1.9.0").is_compatible_with(SemVer.parse("2.0.0"))


def test_semver_prerelease_sorts_before_release():
    assert SemVer.parse("1.0.0-alpha") < SemVer.parse("1.0.0")
    assert SemVer.parse("1.0.0") > SemVer.parse("1.0.0-alpha")


def test_semver_prerelease_equal_versions_are_equal():
    assert SemVer.parse("1.2.3-beta") == SemVer.parse("1.2.3-beta")
    assert SemVer.parse("1.2.3") == SemVer.parse("1.2.3")


def test_semver_is_hashable_and_sortable():
    versions = [SemVer.parse("2.0.0"), SemVer.parse("1.0.0-beta"), SemVer.parse("1.0.0")]
    ordered = sorted(versions)
    assert [str(v) for v in ordered] == ["1.0.0-beta", "1.0.0", "2.0.0"]
    assert len({hash(v) for v in versions}) == 3


def test_satisfies_range_within_bounds():
    assert satisfies_range("1.5.0", "1.0.0", "1.x")


def test_satisfies_range_below_min_fails():
    assert not satisfies_range("0.9.0", "1.0.0", "1.x")


def test_satisfies_range_above_max_fails():
    assert not satisfies_range("2.0.0", "1.0.0", "1.x")


# ---------- Compatibility matrix ----------
def test_compatibility_matrix_reports_compatible_peer():
    matrix = CompatibilityMatrix()
    matrix.declare("tantra-runtime", "1.0.0", "1.x", required=True)
    assert matrix.check("tantra-runtime", "1.2.0") is True


def test_compatibility_matrix_reports_incompatible_peer():
    matrix = CompatibilityMatrix()
    matrix.declare("tantra-runtime", "1.0.0", "1.x", required=True)
    assert matrix.check("tantra-runtime", "2.0.0") is False


def test_compatibility_matrix_unknown_peer_defaults_true():
    matrix = CompatibilityMatrix()
    assert matrix.check("some-unknown-peer", "9.9.9") is True


def test_compatibility_matrix_full_report():
    matrix = CompatibilityMatrix()
    matrix.declare("tantra-runtime", "1.0.0", "1.x", required=True)
    matrix.declare("bhiv.integration.bucket", "0.1.0", None, required=False)
    report = matrix.report({"tantra-runtime": "1.5.0"})
    assert report["tantra-runtime"]["status"] == "compatible"
    assert report["bhiv.integration.bucket"]["status"] == "absent"
