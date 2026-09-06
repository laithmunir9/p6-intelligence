"""Adapters from existing analysis results into the versioned report contract."""

from __future__ import annotations

from typing import Any

from p6intel.impact.analysis import ImpactReport as AnalysisImpactReport, RelationshipChange
from p6intel.models.domain import NormalizedProject, WBSNode
from p6intel.reconcile.activities import ReconciliationResult
from .evidence import EvidenceRegistry
from .models import (
    ActivityChangeReport, ActivityMetadata, ComparisonMetadata, ComparisonReport, EvidenceReference,
    ImpactReport, MilestoneReport, PathReport, ProjectReport, RelationshipChangeReport,
    RelationshipIdentity, ReportWarning, ScheduleMetadata, UncertaintyReport,
    UncertainMatchReport,
)


def _register_dict(registry: EvidenceRegistry, side: str, value: dict[str, Any] | None) -> EvidenceReference | None:
    return registry.register(side, value) if value else None


def _wbs_names(project: NormalizedProject) -> dict[str, str]:
    names: dict[str, str] = {}

    def visit(node: WBSNode) -> None:
        if node.wbs_id and node.name:
            names[node.wbs_id] = node.name
        for child in node.children:
            visit(child)

    for root in project.wbs:
        visit(root)
    return names


def _activity_registry(before: NormalizedProject, after: NormalizedProject,
                       reconciliation: ReconciliationResult, registry: EvidenceRegistry
                       ) -> dict[str, ActivityMetadata]:
    by_before = {match.get("before_activity_id"): match for match in reconciliation.matches
                 if match.get("before_activity_id")}
    by_after = {match.get("after_activity_id"): match for match in reconciliation.matches
                if match.get("after_activity_id")}
    result: dict[str, ActivityMetadata] = {}
    for side, project, matches in (("before", before, by_before), ("after", after, by_after)):
        wbs_names = _wbs_names(project)
        for activity in sorted(project.activities, key=lambda value: value.activity_id or ""):
            if not activity.activity_id:
                continue
            match = matches.get(activity.activity_id, {})
            counterpart = (match.get("after_activity_id") if side == "before"
                           else match.get("before_activity_id"))
            reference = _register_dict(registry, side,
                                       activity.source_record.model_dump(mode="json") if activity.source_record else None)
            key = f"{side}:{activity.activity_id}"
            result[key] = ActivityMetadata(
                side=side, activity_id=activity.activity_id, name=activity.name,
                wbs_id=activity.wbs_id, wbs_name=wbs_names.get(activity.wbs_id or ""),
                is_milestone=activity.is_milestone, milestone_type=activity.task_type,
                status=activity.status, change_status=match.get("status"),
                counterpart_activity_id=counterpart, confidence=match.get("confidence"),
                evidence_refs=[reference] if reference else [])
    return result


def _relationship_report(change: RelationshipChange, registry: EvidenceRegistry, occurrence: int) -> RelationshipChangeReport:
    def identity(value: dict[str, Any] | None) -> RelationshipIdentity | None:
        if value is None:
            return None
        return RelationshipIdentity(predecessor_id=value.get("predecessor_id"), successor_id=value.get("successor_id"),
                                    relationship_type=value.get("relationship_type"), lag_hours=value.get("lag_hours"),
                                    occurrence=occurrence)

    refs = []
    before_ref = _register_dict(registry, "before", change.before.get("source_record") if change.before else None)
    after_ref = _register_dict(registry, "after", change.after.get("source_record") if change.after else None)
    refs.extend(ref for ref in (before_ref, after_ref) if ref)
    return RelationshipChangeReport(status=change.status, identity_before=identity(change.before),
                                    identity_after=identity(change.after), ambiguous=change.ambiguous, evidence_refs=refs)


def build_project_report(reconciliation: ReconciliationResult, impact: AnalysisImpactReport | None,
                         registry: EvidenceRegistry, before_project: NormalizedProject | None = None,
                         after_project: NormalizedProject | None = None) -> ProjectReport:
    activity_changes = []
    for match in reconciliation.matches:
        refs = []
        before_ref = _register_dict(registry, "before", match.get("before_source_record"))
        after_ref = _register_dict(registry, "after", match.get("after_source_record"))
        refs.extend(ref for ref in (before_ref, after_ref) if ref)
        activity_changes.append(ActivityChangeReport(
            before_activity_id=match.get("before_activity_id"), after_activity_id=match.get("after_activity_id"),
            status=match["status"], confidence=match["confidence"], changes=match.get("changes", {}), evidence_refs=refs))

    relationship_reports = []
    if impact:
        for relationship in impact.relationship_changes:
            relationship_reports.append(_relationship_report(relationship, registry, relationship.occurrence))

    activity_metadata = (_activity_registry(before_project, after_project, reconciliation, registry)
                         if before_project is not None and after_project is not None else {})
    impacts = []
    warnings = []
    if impact:
        for item in impact.impacts:
            path_reports = []
            for evidence in item.get("path_evidence", []):
                side = "before" if item["change_status"] == "DELETED" else "after"
                node_refs = {node_id: ref for node_id, raw in evidence.get("node_source_records", {}).items()
                             if (ref := _register_dict(registry, side, raw))}
                edge_refs = [ref for raw in evidence.get("edge_source_records", [])
                             if (ref := _register_dict(registry, side, raw))]
                node_metadata_refs = {node_id: f"{side}:{node_id}" for node_id in evidence["path"]
                                      if f"{side}:{node_id}" in activity_metadata}
                path_reports.append(PathReport(activity_ids=evidence["path"],
                                               node_metadata_refs=node_metadata_refs,
                                               node_evidence_refs=node_refs, edge_evidence_refs=edge_refs))
            milestone_reports = [MilestoneReport(activity_id=milestone_id)
                                 for milestone_id in item.get("downstream_milestones", [])]
            impacts.append(ImpactReport(source_activity=item["source_activity"], change_status=item["change_status"],
                                        confidence=item["confidence"], downstream_activity_count=item["downstream_activity_count"],
                                        changed_downstream_activities=item.get("changed_downstream_activities", []),
                                        downstream_milestones=milestone_reports,
                                        relationship_changes=relationship_reports, paths=path_reports,
                                        uncertain=item.get("uncertain", False)))
        if impact.uncertain_matches:
            warnings.append(ReportWarning(code="UNCERTAIN_MATCHES",
                                          message="Some activity identities were uncertain and excluded from impact analysis."))
    uncertain_reports = []
    if impact:
        for match in impact.uncertain_matches:
            refs = []
            before_ref = _register_dict(registry, "before", match.get("before_source_record"))
            after_ref = _register_dict(registry, "after", match.get("after_source_record"))
            refs.extend(reference for reference in (before_ref, after_ref) if reference)
            uncertain_reports.append(UncertainMatchReport(before_activity_id=match.get("before_activity_id"),
                                                          after_activity_id=match.get("after_activity_id"),
                                                          confidence=match["confidence"], evidence_refs=refs))
    uncertainty = UncertaintyReport(matches=uncertain_reports, excluded_from_impact=True) if uncertain_reports else None
    return ProjectReport(project_id=reconciliation.project_id, activity_changes=activity_changes,
                          activity_metadata=activity_metadata,
                          relationship_changes=relationship_reports, impacts=impacts,
                          uncertainty=uncertainty, warnings=warnings)


def build_comparison_report(comparison: ComparisonMetadata, projects: list[ProjectReport],
                            registry: EvidenceRegistry, warnings: list[ReportWarning] | None = None) -> ComparisonReport:
    return ComparisonReport(comparison=comparison, projects=projects, warnings=warnings or [],
                             evidence=registry.model_dump())
