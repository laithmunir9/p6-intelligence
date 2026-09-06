from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class XERRow(BaseModel):
    model_config = ConfigDict(extra="allow")


class ProjectRow(XERRow):
    proj_id: str | None = None
    proj_short_name: str | None = None
    proj_name: str | None = None
    plan_start_date: str | None = None
    plan_end_date: str | None = None
    clndr_id: str | None = None


class WBSRow(XERRow):
    wbs_id: str | None = None
    proj_id: str | None = None
    parent_wbs_id: str | None = None
    wbs_short_name: str | None = None
    wbs_name: str | None = None


class ActivityRow(XERRow):
    task_id: str | None = None
    proj_id: str | None = None
    wbs_id: str | None = None
    task_code: str | None = None
    task_name: str | None = None
    status_code: str | None = None
    task_type: str | None = None
    target_start_date: str | None = None
    target_end_date: str | None = None
    act_start_date: str | None = None
    act_end_date: str | None = None
    remain_drtn_hr_cnt: str | None = None
    total_float_hr_cnt: str | None = None
    critical_flag: str | None = None


class RelationshipRow(XERRow):
    task_id: str | None = None
    pred_task_id: str | None = None
    pred_type: str | None = None
    lag_hr_cnt: str | None = None


class CalendarRow(XERRow):
    clndr_id: str | None = None
    clndr_name: str | None = None
    clndr_type: str | None = None
    default_flag: str | None = None
