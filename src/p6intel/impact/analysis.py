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
    occurrence: int = 0
    ambiguous: bool = False

    def model_dump(self) -> dict[str, Any]:
        return {"status": self.status, "before": self.before, "after": self.after,
                "predecessor_id": self.predecessor_id, "successor_id": self.successor_id,
                "occurrence": self.occurrence, "ambiguous": self.ambiguous}


@dataclass
class ImpactReport:
    project_id: str | None
    impacts: list[dict[str, Any]]
    relationship_changes: list[RelationshipChange]
    uncertain_matches: list[ActivityMatch]
    traversal_limit_reached: bool = False
    path_limit_reached: bool = False

    def model_dump(self) -> dict[str, Any]:
        return {"project_id": self.project_id, "impacts": self.impacts,
                "relationship_changes": [change.model_dump() for change in self.relationship_changes],
                "uncertain_matches": self.uncertain_matches,
                "traversal_limit_reached": self.traversal_limit_reached,
                "path_limit_reached": self.path_limit_reached}


def _edge_key(predecessor: str | None, successor: str | None) -> tuple[str | None, str | None]:
    return predecessor, successor


def compare_relationships(before: NormalizedProject, after: NormalizedProject,
                          reconciliation: ReconciliationResult) -> list[RelationshipChange]:
    """Compare edges using canonical endpoints and conservative duplicate pairing."""
    mapping = {match["before_activity_id"]: match["after_activity_id"]
               for match in reconciliation.matches
               if match["before_activity_id"] and match["after_activity_id"] and match["status"] != "UNCERTAIN"}

    def describe(relationship, predecessor: str | None, successor: str | None) -> dict[str, Any]:
        return {"predecessor_id": predecessor, "successor_id": successor,
                "relationship_type": relationship.relationship_type,
                "lag_hours": relationship.lag_hours,
                "source_record": relationship.source_record.model_dump(mode="json") if relationship.source_record else None}

    before_edges: dict[tuple[str | None, str | None], list[dict[str, Any]]] = {}
    for relationship in before.relationships:
        key = _edge_key(mapping.get(relationship.predecessor_id), mapping.get(relationship.successor_id))
        before_edges.setdefault(key, []).append(describe(relationship, *key))
    after_edges: dict[tuple[str | None, str | None], list[dict[str, Any]]] = {}
    for relationship in after.relationships:
        key = _edge_key(relationship.predecessor_id, relationship.successor_id)
        after_edges.setdefault(key, []).append(describe(relationship, *key))

    changes: list[RelationshipChange] = []
    for key in sorted(set(before_edges) | set(after_edges), key=str):
        old_list = sorted(before_edges.get(key, []), key=lambda edge: (edge["relationship_type"] or "", edge["lag_hours"] or ""))
        new_list = sorted(after_edges.get(key, []), key=lambda edge: (edge["relationship_type"] or "", edge["lag_hours"] or ""))
        paired_old: set[int] = set()
        paired_new: set[int] = set()
        occurrence = 0
        # Exact signatures are paired first, so unchanged duplicate edges are stable.
        for old_index, old in enumerate(old_list):
            candidates = [new_index for new_index, new in enumerate(new_list)
                          if new_index not in paired_new and
                          (old["relationship_type"], old["lag_hours"]) == (new["relationship_type"], new["lag_hours"])]
            if len(candidates) == 1:
                new_index = candidates[0]
                new = new_list[new_index]
                paired_old.add(old_index); paired_new.add(new_index)
                changes.append(RelationshipChange("UNCHANGED", old, new, key[0], key[1], occurrence))
                occurrence += 1
        remaining_old = [old for index, old in enumerate(old_list) if index not in paired_old]
        remaining_new = [new for index, new in enumerate(new_list) if index not in paired_new]
        ambiguous = len(remaining_old) > 1 or len(remaining_new) > 1
        pair_count = min(len(remaining_old), len(remaining_new))
        for index in range(pair_count):
            changes.append(RelationshipChange("UNCERTAIN" if ambiguous else "MODIFIED",
                                              remaining_old[index], remaining_new[index], key[0], key[1], occurrence, ambiguous))
            occurrence += 1
        for old in remaining_old[pair_count:]:
            changes.append(RelationshipChange("DELETED", old, None, key[0], key[1], occurrence, ambiguous))
            occurrence += 1
        for new in remaining_new[pair_count:]:
            changes.append(RelationshipChange("ADDED", None, new, key[0], key[1], occurrence, ambiguous))
            occurrence += 1
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
    traversal_limit_reached = False
    path_limit_reached = False

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
        traversal_limit_reached |= graph.last_query.truncated
        changed_downstream = sorted(set(downstream) & (changed_before_ids if status == "DELETED" else changed_after_ids))
        milestone_ids = [node_id for node_id in downstream if graph.nodes[node_id].is_milestone]
        paths = graph.paths_to_milestones(source_id)
        path_limit_reached |= graph.last_query.truncated
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
    return ImpactReport(after.metadata.project_id, impacts, relationship_changes, uncertain,
                         traversal_limit_reached, path_limit_reached)
