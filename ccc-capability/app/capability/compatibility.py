from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Optional

_SEMVER_RE = re.compile(
    r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)(?:-(?P<pre>[0-9A-Za-z.-]+))?$"
)

class InvalidVersionError(Exception):
    pass


@dataclass(frozen=True, order=False)
class SemVer:
    major: int
    minor: int
    patch: int
    pre: Optional[str] = None

    @classmethod
    def parse(cls, version: str) -> "SemVer":
        m = _SEMVER_RE.match(version.strip())
        if not m:
            raise InvalidVersionError(f"'{version}' is not a valid semantic version")
        return cls(
            major=int(m.group("major")),
            minor=int(m.group("minor")),
            patch=int(m.group("patch")),
            pre=m.group("pre"),
        )

    def as_tuple(self) -> tuple[int, int, int]:
        return (self.major, self.minor, self.patch)

    def __str__(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        return f"{base}-{self.pre}" if self.pre else base

    def _sort_key(self) -> tuple:
        # Per semver precedence rules: a pre-release version has LOWER
        # precedence than the associated normal version (e.g. 1.0.0-alpha
        # < 1.0.0). We encode "has no pre-release" as 1 and "has a
        # pre-release" as 0 so releases sort after their pre-releases;
        # among pre-releases, compare the pre-release string itself.
        return (self.major, self.minor, self.patch, 0 if self.pre else 1, self.pre or "")

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SemVer):
            return NotImplemented
        return self._sort_key() == other._sort_key()

    def __hash__(self) -> int:
        return hash(self._sort_key())

    def __lt__(self, other: "SemVer") -> bool:
        return self._sort_key() < other._sort_key()

    def __le__(self, other: "SemVer") -> bool:
        return self._sort_key() <= other._sort_key()

    def __gt__(self, other: "SemVer") -> bool:
        return self._sort_key() > other._sort_key()

    def __ge__(self, other: "SemVer") -> bool:
        return self._sort_key() >= other._sort_key()

    def is_compatible_with(self, other: "SemVer") -> bool:
        """Same MAJOR = compatible, per this project's semver_policy
        (MAJOR bumps are the only breaking-change signal)."""
        return self.major == other.major


def satisfies_range(version: str, min_version: str, max_version: Optional[str] = None) -> bool:
    """Check `min_version <= version` and, if given, `version <= max_version`
    (max_version may be a bare major like '1.x', treated as < next major)."""
    v = SemVer.parse(version)
    vmin = SemVer.parse(min_version)
    if v < vmin:
        return False
    if max_version:
        if max_version.endswith(".x"):
            max_major = int(max_version.split(".")[0])
            return v.major <= max_major
        vmax = SemVer.parse(max_version)
        if v > vmax:
            return False
    return True


@dataclass
class CompatibilityEntry:
    peer_name: str
    min_version: str
    max_version: Optional[str] = None
    required: bool = False


class CompatibilityMatrix:
    """Declares, for each known peer/runtime, the version range this
    capability is known to work with. Distinct from the dependency graph:
    the graph is about *structure* (who needs whom), this is about
    *version* compatibility once structurally attached."""

    def __init__(self):
        self._entries: dict[str, CompatibilityEntry] = {}

    def declare(self, peer_name: str, min_version: str, max_version: Optional[str] = None, required: bool = False) -> None:
        self._entries[peer_name] = CompatibilityEntry(peer_name, min_version, max_version, required)

    def check(self, peer_name: str, peer_version: str) -> bool:
        entry = self._entries.get(peer_name)
        if entry is None:
            # Unknown peer: neither declared compatible nor incompatible.
            return True
        return satisfies_range(peer_version, entry.min_version, entry.max_version)

    def required_peers(self) -> list[str]:
        return [name for name, e in self._entries.items() if e.required]

    def report(self, live_versions: dict[str, str]) -> dict[str, dict]:
        """Given a map of peer_name -> observed version, return a full
        compatibility report — used by the health endpoint and by
        upgrade-readiness checks."""
        out = {}
        for name, entry in self._entries.items():
            observed = live_versions.get(name)
            if observed is None:
                out[name] = {"status": "absent", "required": entry.required}
                continue
            ok = satisfies_range(observed, entry.min_version, entry.max_version)
            out[name] = {
                "status": "compatible" if ok else "incompatible",
                "observed_version": observed,
                "min_version": entry.min_version,
                "max_version": entry.max_version,
                "required": entry.required,
            }
        return out
