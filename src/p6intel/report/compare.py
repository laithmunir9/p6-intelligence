"""Composition service for complete deterministic schedule comparison reports."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from p6intel.graph import DependencyGraph
from p6intel.impact import analyze_impact
from p6intel.models.domain import NormalizedExport, NormalizedProject
from p6intel.normalize import normalize
from p6intel.parser import parse_xer
from p6intel.reconcile import ReconciliationConfig, reconcile
from .evidence import EvidenceRegistry
from .models import (
    ComparisonMetadata, ComparisonReport, EvidenceReference, ProjectReport,
    ReportWarning, ScheduleMetadata, UnresolvedRelationshipReport,
)
from .serialize import build_comparison_report, build_project_report


class InvalidXERInput(ValueError):
    """Raised when bytes do not contain a recognizable XER project export."""


def _project_id(project: NormalizedProject) -> str | None:
    return project.metadata.project_id


def _metadata(project: NormalizedProject, side: str, registry: EvidenceRegistry) -> tuple[EvidenceReference | None, list[ReportWarning]]:
    warnings = []
    if not project.metadata.project_id or not project.metadata.name:
        warnings.append(ReportWarning(code="MISSING_PROJECT_METADATA", message="Project ID or name is missing",
                                      project_id=project.metadata.project_id))
    reference = registry.register(side, project.metadata.source_record) if project.metadata.source_record else None
    return reference, warnings


def _add_unresolved(project: NormalizedProject, side: str, report: ProjectReport,
                    registry: EvidenceRegistry) -> None:
    for relationship in project.relationships:
        if relationship.resolved:
            continue
        reference = registry.register(side, relationship.source_record) if relationship.source_record else None
        report.unresolved_relationships.append(UnresolvedRelationshipReport(
            predecessor_id=relationship.predecessor_id, successor_id=relationship.successor_id,
            relationship_type=relationship.relationship_type, lag_hours=relationship.lag_hours,
            reason="predecessor or successor activity is not present in the normalized project",
            evidence_refs=[reference] if reference else []))
    if report.unresolved_relationships:
        report.warnings.append(ReportWarning(
            code="UNRESOLVED_RELATIONSHIP", severity="WARNING",
            message="Unresolved relationships limit graph analysis", project_id=report.project_id,
            evidence_refs=[reference for item in report.unresolved_relationships for reference in item.evidence_refs]))


def _add_graph_warnings(before: NormalizedProject, after: NormalizedProject, report: ProjectReport,
                        impact, max_paths: int, max_traversals: int) -> None:
    for side, project in (("before", before), ("after", after)):
        graph = DependencyGraph.from_project(project, max_paths=max_paths, max_traversals=max_traversals)
        if graph.cycles():
            report.warnings.append(ReportWarning(code="CYCLE_DETECTED", message=f"Cycle detected in {side} dependency graph",
                                                 project_id=report.project_id))
    if impact.traversal_limit_reached:
        report.warnings.append(ReportWarning(code="TRAVERSAL_LIMIT_REACHED", message="Graph traversal limit reached",
                                             project_id=report.project_id))
    if impact.path_limit_reached:
        report.warnings.append(ReportWarning(code="PATH_LIMIT_REACHED", message="Graph path limit reached",
                                             project_id=report.project_id))


def _project_report_for_unmatched(project: NormalizedProject, status: str, side: str,
                                  registry: EvidenceRegistry) -> ProjectReport:
    reference = registry.register(side, project.metadata.source_record) if project.metadata.source_record else None
    return ProjectReport(project_id=_project_id(project), status=status,
                         evidence_refs=[reference] if reference else [],
                         warnings=[ReportWarning(code=f"PROJECT_{status}", message=f"Project is {status.lower()}",
                                                 project_id=_project_id(project), evidence_refs=[reference] if reference else [])])


def _schedule_metadata(source_id: str, source_name: str | None, project_count: int) -> ScheduleMetadata:
    return ScheduleMetadata(source_id=source_id, source_name=source_name, project_count=project_count)


def compare_schedules(before: NormalizedExport, after: NormalizedExport,
                      before_metadata: ScheduleMetadata | None = None,
                      after_metadata: ScheduleMetadata | None = None,
                      reconciliation_config: ReconciliationConfig | None = None,
                      max_paths: int = 10_000, max_traversals: int = 100_000) -> ComparisonReport:
    """Compose existing deterministic services into one complete comparison report."""
    registry = EvidenceRegistry()
    before_by_id = {_project_id(project): project for project in before.projects}
    after_by_id = {_project_id(project): project for project in after.projects}
    project_reports: list[ProjectReport] = []
    for project_id in sorted(set(before_by_id) | set(after_by_id), key=lambda value: value or ""):
        before_project, after_project = before_by_id.get(project_id), after_by_id.get(project_id)
        if before_project is None:
            project_reports.append(_project_report_for_unmatched(after_project, "ADDED", "after", registry))
            continue
        if after_project is None:
            project_reports.append(_project_report_for_unmatched(before_project, "DELETED", "before", registry))
            continue
        reconciliation = reconcile(before_project, after_project, reconciliation_config)
        impact = analyze_impact(before_project, after_project, reconciliation,
                                max_paths=max_paths, max_traversals=max_traversals)
        report = build_project_report(reconciliation, impact, registry, before_project, after_project)
        before_reference, before_warnings = _metadata(before_project, "before", registry)
        after_reference, after_warnings = _metadata(after_project, "after", registry)
        report.evidence_refs.extend(reference for reference in (before_reference, after_reference) if reference)
        report.warnings.extend(before_warnings + after_warnings)
        _add_unresolved(before_project, "before", report, registry)
        _add_unresolved(after_project, "after", report, registry)
        _add_graph_warnings(before_project, after_project, report, impact, max_paths, max_traversals)
        project_reports.append(report)
    comparison = ComparisonMetadata(
        before=before_metadata or _schedule_metadata("before", None, len(before.projects)),
        after=after_metadata or _schedule_metadata("after", None, len(after.projects)))
    return build_comparison_report(comparison, project_reports, registry)


def compare_files(before: str | Path, after: str | Path, **kwargs: Any) -> ComparisonReport:
    """Filesystem wrapper; all comparison logic remains in ``compare_schedules``."""
    before_path, after_path = Path(before), Path(after)
    before_bytes, after_bytes = before_path.read_bytes(), after_path.read_bytes()
    before_export, after_export = normalize(parse_xer(before_bytes)), normalize(parse_xer(after_bytes))
    before_metadata = _schedule_metadata(hashlib.sha256(before_bytes).hexdigest(), before_path.name, len(before_export.projects))
    after_metadata = _schedule_metadata(hashlib.sha256(after_bytes).hexdigest(), after_path.name, len(after_export.projects))
    return compare_schedules(before_export, after_export, before_metadata, after_metadata, **kwargs)


def compare_bytes(before: bytes, after: bytes, before_name: str | None = None,
                 after_name: str | None = None, **kwargs: Any) -> ComparisonReport:
    """Compare in-memory XER exports without creating persistent temporary files."""
    if not before or not after:
        raise InvalidXERInput("empty XER input")
    before_parsed, after_parsed = parse_xer(before), parse_xer(after)
    if "PROJECT" not in before_parsed.tables or "PROJECT" not in after_parsed.tables:
        raise InvalidXERInput("XER export has no PROJECT records")
    before_export, after_export = normalize(before_parsed), normalize(after_parsed)
    if not before_export.projects or not after_export.projects:
        raise InvalidXERInput("XER export has no projects")
    before_metadata = _schedule_metadata(hashlib.sha256(before).hexdigest(), before_name, len(before_export.projects))
    after_metadata = _schedule_metadata(hashlib.sha256(after).hexdigest(), after_name, len(after_export.projects))
    return compare_schedules(before_export, after_export, before_metadata, after_metadata, **kwargs)
