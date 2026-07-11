from __future__ import annotations
from dataclasses import dataclass, field

class DependencyCycleError(Exception):
    def __init__(self, cycle: list[str]):
        self.cycle = cycle
        super().__init__(f"Dependency cycle detected: {' -> '.join(cycle)}")


class UnknownDependencyError(Exception):
    def __init__(self, node: str, missing: str):
        super().__init__(f"'{node}' declares a dependency on unknown node '{missing}'")


@dataclass
class DependencyGraph:
    """A simple directed graph: node -> set of nodes it depends on."""

    edges: dict[str, set[str]] = field(default_factory=dict)

    def add_node(self, node: str) -> None:
        self.edges.setdefault(node, set())

    def add_dependency(self, node: str, depends_on: str) -> None:
        self.add_node(node)
        self.add_node(depends_on)
        self.edges[node].add(depends_on)

    def validate(self, *, allow_unknown: bool = True) -> None:
        """Raise DependencyCycleError if any cycle exists."""
        if not allow_unknown:
            for node, deps in self.edges.items():
                for dep in deps:
                    if dep not in self.edges:
                        raise UnknownDependencyError(node, dep)

        WHITE, GRAY, BLACK = 0, 1, 2
        color = {n: WHITE for n in self.edges}
        path: list[str] = []

        def visit(node: str) -> None:
            color[node] = GRAY
            path.append(node)
            for dep in self.edges.get(node, set()):
                if color.get(dep, WHITE) == GRAY:
                    cycle_start = path.index(dep)
                    raise DependencyCycleError(path[cycle_start:] + [dep])
                if color.get(dep, WHITE) == WHITE:
                    visit(dep)
            path.pop()
            color[node] = BLACK

        for node in list(self.edges):
            if color[node] == WHITE:
                visit(node)

    def topological_order(self) -> list[str]:
        """Return nodes in a safe initialization order (dependencies first)."""
        self.validate()
        visited: set[str] = set()
        order: list[str] = []

        def visit(node: str) -> None:
            if node in visited:
                return
            visited.add(node)
            for dep in self.edges.get(node, set()):
                visit(dep)
            order.append(node)

        for node in list(self.edges):
            visit(node)
        return order

    def depends_on(self, node: str) -> set[str]:
        return set(self.edges.get(node, set()))

    def dependents_of(self, node: str) -> set[str]:
        """Reverse lookup: who depends on `node`? Used for deprecation impact analysis."""
        return {n for n, deps in self.edges.items() if node in deps}
