"""Versioned, deterministic report contract for future consumers."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


REPORT_SCHEMA_VERSION = "1.0"


class ReportModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceReference(ReportModel):
    evidence_id: str


class EvidenceRecord(ReportModel):
    side: Literal["before", "after"]
    table: str
    line_number: int | None = None
    fields: list[str]
    values: list[str]
    raw_line: str | None = None


class ScheduleMetadata(ReportModel):
    source_id: str
    source_name: str | None = None
    encoding: str | None = None
    project_count: int | None = None


class ComparisonMetadata(ReportModel):
    before: ScheduleMetadata
    after: ScheduleMetadata


class ActivityChangeReport(ReportModel):
    before_activity_id: str | None = None
    after_activity_id: str | None = None
    status: str
    confidence: float
    changes: dict[str, dict[str, Any]] = Field(default_factory=dict)
    evidence_refs: list[EvidenceReference] = Field(default_factory=list)


class RelationshipIdentity(ReportModel):
    predecessor_id: str | None = None
    successor_id: str | None = None
    relationship_type: str | None = None
    lag_hours: str | None = None
    occurrence: int = 0


class RelationshipChangeReport(ReportModel):
    status: str
    identity_before: RelationshipIdentity | None = None
    identity_after: RelationshipIdentity | None = None
    evidence_refs: list[EvidenceReference] = Field(default_factory=list)


class MilestoneReport(ReportModel):
    activity_id: str
    name: str | None = None
    evidence_refs: list[EvidenceReference] = Field(default_factory=list)


class PathReport(ReportModel):
    activity_ids: list[str]
    node_evidence_refs: dict[str, EvidenceReference] = Field(default_factory=dict)
    edge_evidence_refs: list[EvidenceReference] = Field(default_factory=list)


class ImpactReport(ReportModel):
    source_activity: str
    change_status: str
    confidence: float
    downstream_activity_count: int
    changed_downstream_activities: list[str] = Field(default_factory=list)
    downstream_milestones: list[MilestoneReport] = Field(default_factory=list)
    relationship_changes: list[RelationshipChangeReport] = Field(default_factory=list)
    paths: list[PathReport] = Field(default_factory=list)
    evidence_refs: list[EvidenceReference] = Field(default_factory=list)
    uncertain: bool = False


class UncertaintyReport(ReportModel):
    matches: list[dict[str, Any]] = Field(default_factory=list)
    excluded_from_impact: bool = True


class ReportWarning(ReportModel):
    code: str
    message: str
    evidence_refs: list[EvidenceReference] = Field(default_factory=list)


class ProjectReport(ReportModel):
    project_id: str | None = None
    status: Literal["MATCHED", "ADDED", "DELETED"] = "MATCHED"
    activity_changes: list[ActivityChangeReport] = Field(default_factory=list)
    relationship_changes: list[RelationshipChangeReport] = Field(default_factory=list)
    impacts: list[ImpactReport] = Field(default_factory=list)
    uncertainty: UncertaintyReport | None = None
    warnings: list[ReportWarning] = Field(default_factory=list)


class ComparisonReport(ReportModel):
    schema_version: str = REPORT_SCHEMA_VERSION
    comparison: ComparisonMetadata
    projects: list[ProjectReport] = Field(default_factory=list)
    warnings: list[ReportWarning] = Field(default_factory=list)
    evidence: dict[str, EvidenceRecord] = Field(default_factory=dict)
