"""Adapters from existing analysis results into the versioned report contract."""

from __future__ import annotations

from typing import Any

from p6intel.impact.analysis import ImpactReport as AnalysisImpactReport, RelationshipChange
from p6intel.reconcile.activities import ReconciliationResult
from .evidence import EvidenceRegistry
from .models import (
    ActivityChangeReport, ComparisonMetadata, ComparisonReport, EvidenceReference,
    ImpactReport, MilestoneReport, PathReport, ProjectReport, RelationshipChangeReport,
    RelationshipIdentity, ReportWarning, ScheduleMetadata, UncertaintyReport,
)


def _register_dict(registry: EvidenceRegistry, side: str, value: dict[str, Any] | None) -> EvidenceReference | None:
    return registry.register(side, value) if value else None


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
                         registry: EvidenceRegistry) -> ProjectReport:
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

    impacts = []
    warnings = []
    if impact:
        for item in impact.impacts:
            path_reports = []
            for evidence in item.get("path_evidence", []):
                node_refs = {node_id: ref for node_id, raw in evidence.get("node_source_records", {}).items()
                             if (ref := _register_dict(registry, "after", raw))}
                edge_refs = [ref for raw in evidence.get("edge_source_records", [])
                             if (ref := _register_dict(registry, "after", raw))]
                path_reports.append(PathReport(activity_ids=evidence["path"], node_evidence_refs=node_refs,
                                               edge_evidence_refs=edge_refs))
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
    uncertainty = UncertaintyReport(matches=list(impact.uncertain_matches), excluded_from_impact=True) if impact and impact.uncertain_matches else None
    return ProjectReport(project_id=reconciliation.project_id, activity_changes=activity_changes,
                          relationship_changes=relationship_reports, impacts=impacts,
                          uncertainty=uncertainty, warnings=warnings)


def build_comparison_report(comparison: ComparisonMetadata, projects: list[ProjectReport],
                            registry: EvidenceRegistry, warnings: list[ReportWarning] | None = None) -> ComparisonReport:
    return ComparisonReport(comparison=comparison, projects=projects, warnings=warnings or [],
                             evidence=registry.model_dump())
