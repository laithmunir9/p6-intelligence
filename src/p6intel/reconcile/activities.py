"""Conservative, deterministic activity reconciliation between normalized exports."""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
import re
from typing import Any

from p6intel.models.domain import Activity, NormalizedExport, NormalizedProject


@dataclass(frozen=True)
class ReconciliationConfig:
    fuzzy_threshold: float = 0.78
    ambiguity_margin: float = 0.08


class ActivityMatch(dict):
    """JSON-shaped result kept as a dict for easy API and CLI serialization."""


@dataclass
class ReconciliationResult:
    project_id: str | None
    matches: list[ActivityMatch]

    def model_dump(self) -> dict[str, Any]:
        return {"project_id": self.project_id, "matches": list(self.matches)}


@dataclass
class MultiReconciliationResult:
    projects: list[ReconciliationResult]
    uncertain_matches: list[ActivityMatch]
    unmatched_before_project_ids: list[str | None] = field(default_factory=list)
    unmatched_after_project_ids: list[str | None] = field(default_factory=list)

    def model_dump(self) -> dict[str, Any]:
        return {"projects": [project.model_dump() for project in self.projects],
                "uncertain_matches": self.uncertain_matches,
                "unmatched_before_project_ids": self.unmatched_before_project_ids,
                "unmatched_after_project_ids": self.unmatched_after_project_ids}


def _text(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().casefold())


def _project(value: NormalizedProject | NormalizedExport) -> NormalizedProject:
    if isinstance(value, NormalizedProject):
        return value
    if len(value.projects) != 1:
        raise ValueError("reconcile() requires a NormalizedProject or a single-project NormalizedExport")
    return value.projects[0]


def _activity_fields(activity: Activity) -> dict[str, str | None]:
    return {"name": activity.name, "wbs_id": activity.wbs_id, "status": activity.status,
            "start_date": activity.target_start, "finish_date": activity.target_finish,
            "actual_start": activity.actual_start, "actual_finish": activity.actual_finish,
            "duration_hours": activity.remaining_duration_hours}


def _neighborhood(project: NormalizedProject, activity_id: str | None) -> tuple[set[str], set[str]]:
    predecessors, successors = set(), set()
    for relationship in project.relationships:
        if relationship.successor_id == activity_id and relationship.predecessor_id:
            predecessors.add(relationship.predecessor_id)
        if relationship.predecessor_id == activity_id and relationship.successor_id:
            successors.add(relationship.successor_id)
    return predecessors, successors


def _context_score(before: Activity, after: Activity, before_project: NormalizedProject, after_project: NormalizedProject) -> float:
    score = 0.0
    if before.wbs_id and before.wbs_id == after.wbs_id:
        score += 0.15
    if before.target_start and before.target_start == after.target_start:
        score += 0.05
    if before.target_finish and before.target_finish == after.target_finish:
        score += 0.05
    if before.remaining_duration_hours and before.remaining_duration_hours == after.remaining_duration_hours:
        score += 0.05
    bp, bs = _neighborhood(before_project, before.activity_id)
    ap, ass = _neighborhood(after_project, after.activity_id)
    if bp and ap and bp & ap:
        score += 0.10
    if bs and ass and bs & ass:
        score += 0.10
    # When IDs changed, compare the names of neighboring activities as a stable
    # structural signal without treating it as proof of identity.
    before_neighbors = {a.name for a in before_project.activities if a.activity_id in bp | bs}
    after_neighbors = {a.name for a in after_project.activities if a.activity_id in ap | ass}
    before_neighbors = {_text(name) for name in before_neighbors}
    after_neighbors = {_text(name) for name in after_neighbors}
    if before_neighbors and after_neighbors and before_neighbors & after_neighbors:
        score += 0.10
    return score


def _source(activity: Activity | None) -> dict[str, Any] | None:
    return activity.source_record.model_dump(mode="json") if activity and activity.source_record else None


def _candidate_score(before: Activity, after: Activity, before_project: NormalizedProject, after_project: NormalizedProject) -> float:
    return min(1.0, 0.70 * SequenceMatcher(None, _text(before.name), _text(after.name)).ratio()
               + _context_score(before, after, before_project, after_project))


def _match_record(before: Activity | None, after: Activity | None, status: str, confidence: float,
                  changes: dict[str, dict[str, str | None]] | None = None) -> ActivityMatch:
    return ActivityMatch(before_activity_id=before.activity_id if before else None,
                         after_activity_id=after.activity_id if after else None,
                         status=status, confidence=round(confidence, 4), changes=changes or {},
                         before_source_record=_source(before), after_source_record=_source(after))


def _matched_record(before: Activity, after: Activity, confidence: float,
                    before_project: NormalizedProject, after_project: NormalizedProject,
                    fuzzy: bool = False, uncertain: bool = False,
                    identity_map: dict[str, str] | None = None) -> ActivityMatch:
    before_fields, after_fields = _activity_fields(before), _activity_fields(after)
    changes = {key: {"before": before_fields[key], "after": after_fields[key]}
               for key in before_fields if before_fields[key] != after_fields[key]}
    before_pred, before_succ = _neighborhood(before_project, before.activity_id)
    after_pred, after_succ = _neighborhood(after_project, after.activity_id)
    identity_map = identity_map or {}
    before_pred = {identity_map.get(value, value) for value in before_pred}
    before_succ = {identity_map.get(value, value) for value in before_succ}
    if before_pred != after_pred:
        changes["predecessors"] = {"before": sorted(before_pred), "after": sorted(after_pred)}
    if before_succ != after_succ:
        changes["successors"] = {"before": sorted(before_succ), "after": sorted(after_succ)}
    status = "UNCERTAIN" if uncertain else ("UNCHANGED" if not changes else "MODIFIED")
    if not uncertain and fuzzy and before.name != after.name and not any(key != "name" for key in changes):
        status = "POSSIBLE_RENAME"
    return _match_record(before, after, status, confidence, changes)


def _reconcile_project(before_project: NormalizedProject, after_project: NormalizedProject,
                       config: ReconciliationConfig) -> list[ActivityMatch]:
    before_by_id = {a.activity_id: a for a in before_project.activities if a.activity_id}
    after_by_id = {a.activity_id: a for a in after_project.activities if a.activity_id}
    unmatched_before = list(before_project.activities)
    unmatched_after = list(after_project.activities)
    pairs: list[tuple[Activity, Activity, float, bool, bool]] = []

    # IDs are authoritative and consumed before any fuzzy candidate generation.
    for activity_id in sorted(set(before_by_id) & set(after_by_id)):
        before, after = before_by_id[activity_id], after_by_id[activity_id]
        pairs.append((before, after, 1.0, False, False))
        unmatched_before.remove(before)
        unmatched_after.remove(after)

    # Exact WBS + normalized name is deterministic after IDs have been consumed.
    for before in sorted(unmatched_before, key=lambda a: (a.activity_id or "", a.name or "")):
        candidates = [after for after in unmatched_after if after.wbs_id == before.wbs_id and _text(after.name) == _text(before.name)]
        if len(candidates) == 1:
            after = candidates[0]
            pairs.append((before, after, 0.98, False, False))
            unmatched_before.remove(before); unmatched_after.remove(after)

    # Fuzzy matches are accepted only above threshold and away from a competing candidate.
    for before in sorted(unmatched_before, key=lambda a: (a.activity_id or "", a.name or "")):
        ranked = sorted((( _candidate_score(before, after, before_project, after_project), after)
                         for after in unmatched_after if after.wbs_id == before.wbs_id), reverse=True, key=lambda item: item[0])
        if not ranked or ranked[0][0] < config.fuzzy_threshold:
            continue
        best_score, after = ranked[0]
        second_score = ranked[1][0] if len(ranked) > 1 else 0.0
        pairs.append((before, after, best_score, True, len(ranked) > 1 and best_score - second_score < config.ambiguity_margin))
        unmatched_before.remove(before); unmatched_after.remove(after)

    identity_map = {before.activity_id: after.activity_id for before, after, _, _, _ in pairs
                     if before.activity_id and after.activity_id}
    results = [_matched_record(before, after, confidence, before_project, after_project, fuzzy, uncertain, identity_map)
               for before, after, confidence, fuzzy, uncertain in pairs]
    results.extend(_match_record(None, after, "ADDED", 1.0) for after in sorted(unmatched_after, key=lambda a: a.activity_id or ""))
    results.extend(_match_record(before, None, "DELETED", 1.0) for before in sorted(unmatched_before, key=lambda a: a.activity_id or ""))
    return results


def reconcile(before: NormalizedProject | NormalizedExport, after: NormalizedProject | NormalizedExport,
              config: ReconciliationConfig | None = None) -> ReconciliationResult:
    before_project, after_project = _project(before), _project(after)
    if before_project.metadata.project_id != after_project.metadata.project_id:
        raise ValueError("reconcile() requires two versions of the same project")
    return ReconciliationResult(before_project.metadata.project_id,
                                _reconcile_project(before_project, after_project, config or ReconciliationConfig()))


def reconcile_exports(before: NormalizedExport, after: NormalizedExport,
                      config: ReconciliationConfig | None = None) -> MultiReconciliationResult:
    """Reconcile all projects sharing an ID and explicitly report uncertain matches."""
    before_by_id = {project.metadata.project_id: project for project in before.projects}
    after_by_id = {project.metadata.project_id: project for project in after.projects}
    results = []
    for project_id in sorted(set(before_by_id) & set(after_by_id), key=lambda value: value or ""):
        results.append(reconcile(before_by_id[project_id], after_by_id[project_id], config))
    uncertain = [match for result in results for match in result.matches if match["status"] == "UNCERTAIN"]
    return MultiReconciliationResult(
        results, uncertain,
        sorted(set(before_by_id) - set(after_by_id), key=lambda value: value or ""),
        sorted(set(after_by_id) - set(before_by_id), key=lambda value: value or ""))
