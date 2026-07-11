from __future__ import annotations
from app.capability.manifest import AuthorityBoundary, load_manifest

class AuthorityViolation(Exception):
    pass


class AuthorityGuard:
    def __init__(self, boundary: AuthorityBoundary):
        self._boundary = boundary

    @classmethod
    def from_manifest(cls) -> "AuthorityGuard":
        return cls(load_manifest().authority_boundary)

    def owns(self, resource_type: str) -> bool:
        return resource_type in self._boundary.owns

    def assert_owns(self, resource_type: str) -> None:
        if not self.owns(resource_type):
            raise AuthorityViolation(
                f"Capability does not own resource type '{resource_type}'; "
                f"owned types: {self._boundary.owns}"
            )

    def assert_action_permitted(self, action_description: str) -> None:
        for forbidden in self._boundary.will_not:
            if forbidden.lower() in action_description.lower():
                raise AuthorityViolation(
                    f"Action '{action_description}' falls within a declared "
                    f"'will_not' boundary: '{forbidden}'"
                )

    @property
    def escalation_contact(self) -> str | None:
        return self._boundary.escalation_contact
