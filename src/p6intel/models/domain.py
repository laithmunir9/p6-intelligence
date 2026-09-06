from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class SourceRecord(DomainModel):
    table: str
    fields: list[str]
    values: list[str]
    line_number: int
    raw_line: str


class ProjectMetadata(DomainModel):
    project_id: str | None = None
    short_name: str | None = None
    name: str | None = None
    planned_start: str | None = None
    planned_finish: str | None = None
    calendar_id: str | None = None
    source_record: SourceRecord | None = None


class WBSNode(DomainModel):
    wbs_id: str | None = None
    project_id: str | None = None
    parent_wbs_id: str | None = None
    short_name: str | None = None
    name: str | None = None
    children: list["WBSNode"] = Field(default_factory=list)


class Activity(DomainModel):
    activity_id: str | None = None
    project_id: str | None = None
    wbs_id: str | None = None
    code: str | None = None
    name: str | None = None
    status: str | None = None
    task_type: str | None = None
    total_float_hours: str | None = None
    critical_flag: str | None = None
    target_start: str | None = None
    target_finish: str | None = None
    actual_start: str | None = None
    actual_finish: str | None = None
    remaining_duration_hours: str | None = None
    source_record: SourceRecord | None = None

    @property
    def is_milestone(self) -> bool:
        return (self.task_type or "").casefold() in {"tt_mile", "tt_finmile", "tt_startmile"}


class Relationship(DomainModel):
    predecessor_id: str | None = None
    successor_id: str | None = None
    predecessor: Activity | None = None
    successor: Activity | None = None
    relationship_type: str | None = None
    lag_hours: str | None = None
    resolved: bool = False
    source_record: SourceRecord | None = None


class Calendar(DomainModel):
    calendar_id: str | None = None
    name: str | None = None
    calendar_type: str | None = None
    is_default: str | None = None


class NormalizedProject(DomainModel):
    metadata: ProjectMetadata
    wbs: list[WBSNode] = Field(default_factory=list)
    activities: list[Activity] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)
    calendars: list[Calendar] = Field(default_factory=list)


class NormalizedExport(DomainModel):
    projects: list[NormalizedProject] = Field(default_factory=list)
    unknown_tables: dict[str, list[dict[str, str | None]]] = Field(default_factory=dict)
    diagnostics: list[dict[str, str | int]] = Field(default_factory=list)
