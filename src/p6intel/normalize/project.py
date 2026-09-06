from __future__ import annotations

from p6intel.models.domain import Activity, Calendar, NormalizedExport, NormalizedProject, ProjectMetadata, Relationship, SourceRecord, WBSNode
from p6intel.models.raw import ActivityRow, CalendarRow, ProjectRow, RelationshipRow, WBSRow
from p6intel.parser.xer import ParsedXER, RawRecord


def _rows(parsed: ParsedXER, name: str) -> list[dict[str, str | None]]:
    table = parsed.tables.get(name)
    return table.records if table else []


def _unknown(row) -> dict[str, str | None]:
    """Carry source columns not mapped into the normalized vocabulary."""
    return {key: value for key, value in (row.model_extra or {}).items() if key != "__extra__"}


def _source(parsed: ParsedXER, table: str, index: int) -> SourceRecord | None:
    table_data = parsed.tables.get(table)
    if table_data is None or index >= len(table_data.raw_records):
        return None
    raw: RawRecord = table_data.raw_records[index]
    return SourceRecord(table=table, fields=raw.fields, values=raw.values,
                        line_number=raw.line_number, raw_line=raw.raw_line)


def normalize(parsed: ParsedXER) -> NormalizedExport:
    projects = [ProjectRow.model_validate(row) for row in _rows(parsed, "PROJECT")]
    wbs = [WBSRow.model_validate(row) for row in _rows(parsed, "PROJWBS")]
    activities = [ActivityRow.model_validate(row) for row in _rows(parsed, "TASK")]
    relationships = [RelationshipRow.model_validate(row) for row in _rows(parsed, "TASKPRED")]
    calendars = [CalendarRow.model_validate(row) for row in _rows(parsed, "CALENDAR")]
    by_project: dict[str | None, NormalizedProject] = {}
    for index, row in enumerate(projects):
        metadata = ProjectMetadata(project_id=row.proj_id, short_name=row.proj_short_name, name=row.proj_name,
                                    planned_start=row.plan_start_date, planned_finish=row.plan_end_date, calendar_id=row.clndr_id,
                                    source_record=_source(parsed, "PROJECT", index))
        by_project[row.proj_id] = NormalizedProject(metadata=metadata)
    if not by_project and (wbs or activities):
        by_project[None] = NormalizedProject(metadata=ProjectMetadata())
    if calendars and not by_project:
        by_project[None] = NormalizedProject(metadata=ProjectMetadata())
    for row in wbs:
        target = by_project.setdefault(row.proj_id, NormalizedProject(metadata=ProjectMetadata(project_id=row.proj_id)))
        target.wbs.append(WBSNode(wbs_id=row.wbs_id, project_id=row.proj_id, parent_wbs_id=row.parent_wbs_id,
                                  short_name=row.wbs_short_name, name=row.wbs_name, **_unknown(row)))
    # Keep roots in ``wbs`` and attach descendants beneath their parent. A missing
    # parent remains a root so malformed/incomplete exports are not discarded.
    for target in by_project.values():
        nodes = {node.wbs_id: node for node in target.wbs if node.wbs_id}
        roots = []
        for node in target.wbs:
            parent = nodes.get(node.parent_wbs_id)
            if parent is not None and parent is not node:
                parent.children.append(node)
            else:
                roots.append(node)
        target.wbs = roots
    for index, row in enumerate(activities):
        target = by_project.setdefault(row.proj_id, NormalizedProject(metadata=ProjectMetadata(project_id=row.proj_id)))
        target.activities.append(Activity(activity_id=row.task_id, project_id=row.proj_id, wbs_id=row.wbs_id,
                                          code=row.task_code, name=row.task_name, status=row.status_code,
                                          task_type=row.task_type, total_float_hours=row.total_float_hr_cnt,
                                          critical_flag=row.critical_flag,
                                          target_start=row.target_start_date, target_finish=row.target_end_date,
                                          actual_start=row.act_start_date, actual_finish=row.act_end_date,
                                          remaining_duration_hours=row.remain_drtn_hr_cnt,
                                          source_record=_source(parsed, "TASK", index), **_unknown(row)))
    for row in calendars:
        # Calendars are often shared; retain them on each normalized project when the export is project-scoped.
        for target in (by_project.values() or [NormalizedProject(metadata=ProjectMetadata())]):
            target.calendars.append(Calendar(calendar_id=row.clndr_id, name=row.clndr_name, calendar_type=row.clndr_type, is_default=row.default_flag))
    activity_map = {a.activity_id: a for target in by_project.values() for a in target.activities if a.activity_id}
    for index, row in enumerate(relationships):
        predecessor, successor = activity_map.get(row.pred_task_id), activity_map.get(row.task_id)
        rel = Relationship(predecessor_id=row.pred_task_id, successor_id=row.task_id, predecessor=predecessor,
                           successor=successor, relationship_type=row.pred_type, lag_hours=row.lag_hr_cnt,
                           resolved=predecessor is not None and successor is not None,
                           source_record=_source(parsed, "TASKPRED", index))
        target = by_project.get(successor.project_id if successor else None)
        if target is None and by_project:
            target = next(iter(by_project.values()))
        if target is None:
            target = by_project.setdefault(None, NormalizedProject(metadata=ProjectMetadata()))
        target.relationships.append(rel)
    return NormalizedExport(projects=list(by_project.values()),
                            unknown_tables={name: table.records for name, table in parsed.unknown_tables.items()},
                            diagnostics=[d.__dict__ for d in parsed.diagnostics])
