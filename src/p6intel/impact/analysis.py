"""Relationship comparison and graph context analysis; never claims schedule causality."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from p6intel.graph import DependencyGraph
from p6intel.models.domain import NormalizedProject
from p6intel.reconcile.activities import ActivityMatch, ReconciliationResult


@dataclass
class RelationshipChange:
    status: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    predecessor_id: str | None
    successor_id: str | None

    def model_dump(self) -> dict[str, Any]:
        return {"status": self.status, "before": self.before, "after": self.after,
                "predecessor_id": self.predecessor_id, "successor_id": self.successor_id}


@dataclass
class ImpactReport:
    project_id: str | None
    impacts: list[dict[str, Any]]
    relationship_changes: list[RelationshipChange]
    uncertain_matches: list[ActivityMatch]

    def model_dump(self) -> dict[str, Any]:
        return {"project_id": self.project_id, "impacts": self.impacts,
                "relationship_changes": [change.model_dump() for change in self.relationship_changes],
                "uncertain_matches": self.uncertain_matches}


def _edge_key(predecessor: str | None, successor: str | None) -> tuple[str | None, str | None]:
    return predecessor, successor


def compare_relationships(before: NormalizedProject, after: NormalizedProject,
                          reconciliation: ReconciliationResult) -> list[RelationshipChange]:
    """Compare edges using the after-version identity for reconciled activities."""
    mapping = {match["before_activity_id"]: match["after_activity_id"]
               for match in reconciliation.matches
               if match["before_activity_id"] and match["after_activity_id"] and match["status"] != "UNCERTAIN"}

    def describe(relationship, predecessor: str | None, successor: str | None) -> dict[str, Any]:
        return {"predecessor_id": predecessor, "successor_id": successor,
                "relationship_type": relationship.relationship_type,
                "lag_hours": relationship.lag_hours,
                "source_record": relationship.source_record.model_dump(mode="json") if relationship.source_record else None}

    before_edges = {}
    for relationship in before.relationships:
        key = _edge_key(mapping.get(relationship.predecessor_id), mapping.get(relationship.successor_id))
        before_edges.setdefault(key, []).append(describe(relationship, *key))
    after_edges = {}
    for relationship in after.relationships:
        key = _edge_key(relationship.predecessor_id, relationship.successor_id)
        after_edges.setdefault(key, []).append(describe(relationship, *key))

    changes = []
    for key in sorted(set(before_edges) | set(after_edges), key=str):
        old_list, new_list = before_edges.get(key, []), after_edges.get(key, [])
        old, new = old_list[0] if old_list else None, new_list[0] if new_list else None
        if old and new:
            status = "UNCHANGED" if (old["relationship_type"], old["lag_hours"]) == (new["relationship_type"], new["lag_hours"]) else "MODIFIED"
        else:
            status = "DELETED" if old else "ADDED"
        changes.append(RelationshipChange(status, old, new, key[0], key[1]))
    return changes


def analyze_impact(before: NormalizedProject, after: NormalizedProject,
                   reconciliation: ReconciliationResult, include_uncertain: bool = False,
                   max_paths: int = 10_000, max_traversals: int = 100_000) -> ImpactReport:
    """Describe graph context for activity changes without inferring causation."""
    uncertain = [match for match in reconciliation.matches if match["status"] == "UNCERTAIN"]
    relationship_changes = compare_relationships(before, after, reconciliation)
    after_graph = DependencyGraph.from_project(after, max_paths=max_paths, max_traversals=max_traversals)
    before_graph = DependencyGraph.from_project(before, max_paths=max_paths, max_traversals=max_traversals)
    changed_after_ids = {match["after_activity_id"] for match in reconciliation.matches
                         if match["status"] in {"MODIFIED", "ADDED", "POSSIBLE_RENAME"} and match["after_activity_id"]}
    changed_before_ids = {match["before_activity_id"] for match in reconciliation.matches
                          if match["status"] == "DELETED" and match["before_activity_id"]}
    if not include_uncertain:
        uncertain_ids = {value for match in uncertain for value in (match["before_activity_id"], match["after_activity_id"]) if value}
        changed_after_ids -= uncertain_ids
        changed_before_ids -= uncertain_ids
    impacts = []

    def evidence_for_paths(graph: DependencyGraph, paths: list[list[str]]) -> list[dict[str, Any]]:
        evidence = []
        for path in paths:
            node_records = {node_id: graph.nodes[node_id].source_record.model_dump(mode="json")
                            for node_id in path if graph.nodes[node_id].source_record}
            edge_records = []
            for predecessor_id, successor_id in zip(path, path[1:]):
                edge_records.extend(
                    edge.source_record.model_dump(mode="json")
                    for edge in graph.edges_between(predecessor_id, successor_id)
                    if edge.source_record)
            evidence.append({"path": path, "node_source_records": node_records,
                             "edge_source_records": edge_records})
        return evidence

    for match in reconciliation.matches:
        status = match["status"]
        if status == "UNCERTAIN" and not include_uncertain:
            continue
        if status not in {"MODIFIED", "ADDED", "DELETED", "POSSIBLE_RENAME", "UNCERTAIN"}:
            continue
        # A conservative project-level rule prevents ambiguous identity from
        # leaking into downstream conclusions through its competing candidates.
        if not include_uncertain and uncertain and status in {"ADDED", "DELETED"}:
            continue
        source_id = match["after_activity_id"] if status != "DELETED" else match["before_activity_id"]
        graph = before_graph if status == "DELETED" else after_graph
        if not source_id or source_id not in graph.nodes:
            continue
        downstream = graph.downstream(source_id).activities
        changed_downstream = sorted(set(downstream) & (changed_before_ids if status == "DELETED" else changed_after_ids))
        milestone_ids = [node_id for node_id in downstream if graph.nodes[node_id].is_milestone]
        paths = graph.paths_to_milestones(source_id)
        impacts.append({"source_activity": source_id, "change_status": status,
                        "confidence": match["confidence"], "uncertain": status == "UNCERTAIN",
                        "downstream_activity_count": len(downstream),
                        "changed_downstream_activities": changed_downstream,
                        "downstream_milestones": sorted(milestone_ids),
                        "relationship_changes": [change.model_dump() for change in relationship_changes
                                                 if change.predecessor_id == source_id or change.successor_id == source_id],
                        "paths": paths,
                        "path_evidence": evidence_for_paths(graph, paths),
                        "source_record": match["after_source_record"] if status != "DELETED" else match["before_source_record"]})
    return ImpactReport(after.metadata.project_id, impacts, relationship_changes, uncertain)
