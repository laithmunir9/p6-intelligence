"""Deterministic dependency graph and bounded traversal operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator

from p6intel.models.domain import Activity, NormalizedProject, Relationship, SourceRecord


_RELATIONSHIP_TYPES = {"FS", "SS", "FF", "SF"}


def _relationship_type(value: str | None) -> str:
    value = (value or "").upper()
    return value.removeprefix("PR_") if value.removeprefix("PR_") in _RELATIONSHIP_TYPES else value


@dataclass(frozen=True)
class DependencyNode:
    activity_id: str
    activity: Activity
    wbs_id: str | None
    status: str | None
    is_milestone: bool
    source_record: SourceRecord | None


@dataclass(frozen=True)
class DependencyEdge:
    predecessor_id: str
    successor_id: str
    relationship_type: str
    lag_hours: str | None
    wbs_id: str | None
    source_record: SourceRecord | None
    resolved: bool


@dataclass
class GraphQueryResult:
    activities: list[str] = field(default_factory=list)
    truncated: bool = False
    cycles: list[list[str]] = field(default_factory=list)

    def __iter__(self) -> Iterator[str]:
        return iter(self.activities)

    def __len__(self) -> int:
        return len(self.activities)


class DependencyGraph:
    def __init__(self, project_id: str | None = None, max_traversals: int = 100_000,
                 max_paths: int = 10_000):
        self.project_id = project_id
        self.max_traversals = max_traversals
        self.max_paths = max_paths
        self.nodes: dict[str, DependencyNode] = {}
        self.edges: list[DependencyEdge] = []
        self._outgoing: dict[str, list[DependencyEdge]] = {}
        self._incoming: dict[str, list[DependencyEdge]] = {}
        self.last_query = GraphQueryResult()

    @classmethod
    def from_project(cls, project: NormalizedProject, **limits: int) -> "DependencyGraph":
        graph = cls(project.metadata.project_id, **limits)
        for activity in project.activities:
            if activity.activity_id:
                graph.add_node(activity)
        for relationship in project.relationships:
            if relationship.predecessor_id and relationship.successor_id:
                graph.add_edge(relationship)
        return graph

    def add_node(self, activity: Activity) -> None:
        if activity.activity_id:
            self.nodes[activity.activity_id] = DependencyNode(
                activity_id=activity.activity_id, activity=activity, wbs_id=activity.wbs_id,
                status=activity.status, is_milestone=activity.is_milestone,
                source_record=activity.source_record)

    def add_edge(self, relationship: Relationship) -> None:
        if not relationship.predecessor_id or not relationship.successor_id:
            return
        edge = DependencyEdge(
            predecessor_id=relationship.predecessor_id,
            successor_id=relationship.successor_id,
            relationship_type=_relationship_type(relationship.relationship_type),
            lag_hours=relationship.lag_hours,
            wbs_id=(self.nodes.get(relationship.successor_id).wbs_id
                    if relationship.successor_id in self.nodes else None),
            source_record=relationship.source_record,
            resolved=relationship.resolved and relationship.predecessor_id in self.nodes and relationship.successor_id in self.nodes)
        self.edges.append(edge)
        if edge.resolved:
            self._outgoing.setdefault(edge.predecessor_id, []).append(edge)
            self._incoming.setdefault(edge.successor_id, []).append(edge)

    def immediate_predecessors(self, activity_id: str) -> list[str]:
        return sorted(edge.predecessor_id for edge in self._incoming.get(activity_id, []))

    def immediate_successors(self, activity_id: str) -> list[str]:
        return sorted(edge.successor_id for edge in self._outgoing.get(activity_id, []))

    def edges_between(self, predecessor_id: str, successor_id: str) -> list[DependencyEdge]:
        """Return all directed edges between two resolved nodes."""
        return [edge for edge in self._outgoing.get(predecessor_id, [])
                if edge.successor_id == successor_id]

    def _reachable(self, activity_id: str, outgoing: bool) -> GraphQueryResult:
        result = GraphQueryResult()
        visited = {activity_id}
        stack = [(activity_id, [activity_id])]
        traversals = 0
        while stack:
            current, path = stack.pop()
            edges = self._outgoing.get(current, []) if outgoing else self._incoming.get(current, [])
            for edge in sorted(edges, key=lambda e: (e.successor_id, e.predecessor_id), reverse=True):
                nxt = edge.successor_id if outgoing else edge.predecessor_id
                traversals += 1
                if traversals > self.max_traversals:
                    result.truncated = True
                    self.last_query = result
                    return result
                if nxt in path:
                    result.cycles.append(path + [nxt])
                    continue
                if nxt not in visited:
                    visited.add(nxt)
                    result.activities.append(nxt)
                    stack.append((nxt, path + [nxt]))
        self.last_query = result
        return result

    def upstream(self, activity_id: str) -> GraphQueryResult:
        return self._reachable(activity_id, outgoing=False)

    def downstream(self, activity_id: str) -> GraphQueryResult:
        return self._reachable(activity_id, outgoing=True)

    def paths(self, source_id: str, target_id: str) -> list[list[str]]:
        paths: list[list[str]] = []
        cycles: list[list[str]] = []
        traversals = 0

        def visit(current: str, path: list[str]) -> None:
            nonlocal traversals
            if len(paths) >= self.max_paths or traversals >= self.max_traversals:
                return
            if current == target_id:
                paths.append(path)
                return
            for edge in sorted(self._outgoing.get(current, []), key=lambda e: e.successor_id):
                traversals += 1
                nxt = edge.successor_id
                if nxt in path:
                    cycles.append(path + [nxt])
                    continue
                visit(nxt, path + [nxt])

        if source_id in self.nodes and target_id in self.nodes:
            visit(source_id, [source_id])
        self.last_query = GraphQueryResult(activities=[], truncated=len(paths) >= self.max_paths or traversals >= self.max_traversals,
                                           cycles=cycles)
        return paths

    def paths_to_milestones(self, source_id: str) -> list[list[str]]:
        paths: list[list[str]] = []
        for activity_id, node in sorted(self.nodes.items()):
            if node.is_milestone and activity_id != source_id:
                paths.extend(self.paths(source_id, activity_id))
                if len(paths) >= self.max_paths:
                    return paths[:self.max_paths]
        return paths

    def connected_components(self) -> list[list[str]]:
        adjacency: dict[str, set[str]] = {node_id: set() for node_id in self.nodes}
        for edge in self.edges:
            if edge.resolved:
                adjacency[edge.predecessor_id].add(edge.successor_id)
                adjacency[edge.successor_id].add(edge.predecessor_id)
        components = []
        unseen = set(adjacency)
        while unseen:
            root = min(unseen)
            component, stack = [], [root]
            unseen.remove(root)
            while stack:
                current = stack.pop()
                component.append(current)
                for neighbor in sorted(adjacency[current], reverse=True):
                    if neighbor in unseen:
                        unseen.remove(neighbor)
                        stack.append(neighbor)
            components.append(sorted(component))
        return sorted(components, key=lambda component: component[0])

    def cycles(self) -> list[list[str]]:
        found: list[list[str]] = []
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(current: str, path: list[str]) -> None:
            visiting.add(current)
            for edge in self._outgoing.get(current, []):
                nxt = edge.successor_id
                if nxt in visiting:
                    start = path.index(nxt) if nxt in path else 0
                    found.append(path[start:] + [nxt])
                elif nxt not in visited:
                    visit(nxt, path + [nxt])
            visiting.remove(current)
            visited.add(current)

        for node_id in sorted(self.nodes):
            if node_id not in visited:
                visit(node_id, [node_id])
        return found
