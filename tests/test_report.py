from __future__ import annotations

import json
from pathlib import Path
import unittest

from p6intel.impact import analyze_impact
from p6intel.models.domain import SourceRecord
from p6intel.normalize import normalize
from p6intel.parser import XERParser
from p6intel.reconcile import reconcile
from p6intel.report import (
    ComparisonMetadata, ComparisonReport, EvidenceRegistry, EvidenceReference,
    ProjectReport, ReportWarning, ScheduleMetadata, build_comparison_report,
    RelationshipChangeReport, RelationshipIdentity, build_project_report,
)


FIXTURES = Path(__file__).parent / "fixtures"


def project(name: str):
    return normalize(XERParser().parse_file(FIXTURES / name)).projects[0]


def milestone_version(activity_id: str, activity_name: str):
    text = "\n".join([
        "%T\tPROJECT", "%F\tproj_id\tproj_name", "%R\tP\tReport",
        "%T\tPROJWBS", "%F\twbs_id\tproj_id\twbs_name", "%R\tW\tP\tWork",
        "%T\tTASK", "%F\ttask_id\tproj_id\twbs_id\ttask_name\ttask_type",
        f"%R\t{activity_id}\tP\tW\t{activity_name}\tTT_Task",
        "%R\tM\tP\tW\tFinish\tTT_Mile",
        "%T\tTASKPRED", "%F\ttask_id\tpred_task_id\tpred_type\tlag_hr_cnt",
        f"%R\tM\t{activity_id}\tPR_FS\t0", "%E",
    ])
    return normalize(XERParser().parse_text(text)).projects[0]


class ReportTests(unittest.TestCase):
    def test_schema_version_and_full_round_trip(self):
        before, after = project("reconcile_before.xer"), project("reconcile_after.xer")
        reconciliation = reconcile(before, after)
        registry = EvidenceRegistry()
        project_report = build_project_report(reconciliation, analyze_impact(before, after, reconciliation), registry)
        report = build_comparison_report(
            ComparisonMetadata(
                before=ScheduleMetadata(source_id="before-xer", source_name="reconcile_before.xer", encoding="utf-8", project_count=1),
                after=ScheduleMetadata(source_id="after-xer", source_name="reconcile_after.xer", encoding="utf-8", project_count=1),
            ), [project_report], registry)
        payload = report.model_dump_json()
        self.assertEqual(json.loads(payload)["schema_version"], "1.1")
        restored = ComparisonReport.model_validate_json(payload)
        self.assertEqual(restored, report)
        self.assertTrue(restored.projects[0].activity_changes)
        self.assertTrue(restored.projects[0].relationship_changes)
        self.assertTrue(restored.evidence)

    def test_activity_metadata_registry_resolves_path_nodes_and_preserves_identity(self):
        before, after = milestone_version("A", "Transformer Delivery"), milestone_version("B", "Transformer Delivery revised")
        report = build_project_report(reconcile(before, after), analyze_impact(before, after, reconcile(before, after)),
                                      EvidenceRegistry(), before, after)
        metadata = report.activity_metadata
        self.assertEqual(metadata["after:B"].name, "Transformer Delivery revised")
        self.assertTrue(metadata["after:M"].is_milestone)
        self.assertEqual(metadata["before:A"].counterpart_activity_id, "B")
        self.assertEqual(metadata["after:B"].counterpart_activity_id, "A")
        path = report.impacts[0].paths[0]
        self.assertEqual(path.node_metadata_refs, {"B": "after:B", "M": "after:M"})
        self.assertTrue(metadata["after:B"].evidence_refs)

    def test_evidence_is_deterministic_deduplicated_and_side_specific(self):
        record = SourceRecord(table="TASK", fields=["task_id"], values=["A1"], line_number=4, raw_line="%R\tA1")
        first = EvidenceRegistry()
        second = EvidenceRegistry()
        before_id = first.register("before", record).evidence_id
        self.assertEqual(before_id, first.register("before", record).evidence_id)
        self.assertEqual(before_id, second.register("before", record).evidence_id)
        after_id = first.register("after", record).evidence_id
        different_id = first.register("before", SourceRecord(table="TASK", fields=["task_id"], values=["A2"], line_number=4, raw_line="%R\tA2")).evidence_id
        self.assertNotEqual(before_id, after_id)
        self.assertNotEqual(before_id, different_id)
        self.assertEqual(len(first), 3)
        self.assertEqual(first.resolve(before_id).side, "before")

    def test_activity_relationship_and_path_evidence_use_references(self):
        before, after = project("reconcile_before.xer"), project("reconcile_after.xer")
        reconciliation = reconcile(before, after)
        registry = EvidenceRegistry()
        report = build_project_report(reconciliation, analyze_impact(before, after, reconciliation), registry)
        modified = next(change for change in report.activity_changes if change.before_activity_id == "A200")
        self.assertIsInstance(modified.evidence_refs[0], EvidenceReference)
        self.assertTrue(all(reference.evidence_id in registry.model_dump() for reference in modified.evidence_refs))
        relationship = next(change for change in report.relationship_changes if change.status == "ADDED")
        self.assertTrue(relationship.evidence_refs)
        self.assertFalse(any(impact.paths for impact in report.impacts))  # fixture has no milestone path

        before, after = milestone_version("A", "Start"), milestone_version("B", "Start renamed")
        reconciliation = reconcile(before, after)
        registry = EvidenceRegistry()
        renamed_report = build_project_report(reconciliation, analyze_impact(before, after, reconciliation), registry)
        path = next(impact for impact in renamed_report.impacts if impact.source_activity == "B").paths[0]
        self.assertEqual(path.activity_ids, ["B", "M"])
        self.assertEqual(len(path.edge_evidence_refs), 1)
        self.assertEqual(registry.resolve(path.edge_evidence_refs[0]).table, "TASKPRED")
        self.assertEqual(set(path.node_evidence_refs), {"B", "M"})

    def test_project_status_uncertainty_unresolved_duplicates_and_warnings_are_modelable(self):
        duplicate_identity = {"predecessor_id": "A", "successor_id": "B", "relationship_type": "FS", "lag_hours": "0", "occurrence": 1}
        duplicate_relationships = [RelationshipChangeReport(
            status="UNCHANGED", identity_before=RelationshipIdentity(**{**duplicate_identity, "occurrence": index}),
            identity_after=RelationshipIdentity(**{**duplicate_identity, "occurrence": index})) for index in (0, 1)]
        report = ComparisonReport(
            comparison=ComparisonMetadata(
                before=ScheduleMetadata(source_id="b"), after=ScheduleMetadata(source_id="a")),
            projects=[ProjectReport(project_id="P1", status="ADDED"), ProjectReport(project_id="P2", status="DELETED")],
            warnings=[ReportWarning(code="UNRESOLVED_RELATIONSHIP", message="Endpoint is not present")],
        )
        self.assertEqual({project.status for project in report.projects}, {"ADDED", "DELETED"})
        self.assertEqual(report.warnings[0].code, "UNRESOLVED_RELATIONSHIP")
        self.assertEqual([relationship.identity_before.occurrence for relationship in duplicate_relationships], [0, 1])

    def test_empty_and_multiple_project_reports_serialize(self):
        metadata = ComparisonMetadata(before=ScheduleMetadata(source_id="b"), after=ScheduleMetadata(source_id="a"))
        empty = build_comparison_report(metadata, [], EvidenceRegistry())
        self.assertEqual(empty.projects, [])
        multi = build_comparison_report(metadata, [ProjectReport(project_id="P1"), ProjectReport(project_id="P2")], EvidenceRegistry())
        self.assertEqual([p.project_id for p in multi.projects], ["P1", "P2"])


if __name__ == "__main__":
    unittest.main()
