from __future__ import annotations

import json
from pathlib import Path
import unittest

from p6intel.graph import DependencyGraph
from p6intel.normalize import normalize
from p6intel.parser import XERParser
from p6intel.report import ComparisonReport, compare_files, compare_schedules


FIXTURES = Path(__file__).parent / "fixtures"


class CompatibilityTests(unittest.TestCase):
    def test_realistic_site_fixture_covers_order_encoding_wbs_calendar_milestones_and_unknowns(self):
        parsed = XERParser().parse_file(FIXTURES / "compatibility_site.xer")
        normalized = normalize(parsed)
        project = normalized.projects[0]
        self.assertEqual(project.metadata.name, "Rénovation – Phase 1")
        self.assertEqual(len(project.calendars), 2)
        self.assertTrue(any(activity.is_milestone for activity in project.activities))
        self.assertEqual(project.wbs[0].children[0].children[0].name, "Piling")
        self.assertEqual(len(project.relationships), 6)
        self.assertIn("UNKNOWN_P6_TABLE", normalized.unknown_tables)
        self.assertEqual(project.activities[0].custom_task_field, "alpha")

    def test_realistic_portfolio_and_update_fixtures(self):
        portfolio = normalize(XERParser().parse_file(FIXTURES / "compatibility_portfolio.xer"))
        self.assertEqual([project.metadata.project_id for project in portfolio.projects], ["P-A", "P-B"])
        before = normalize(XERParser().parse_file(FIXTURES / "compatibility_update_before.xer"))
        after = normalize(XERParser().parse_file(FIXTURES / "compatibility_update_after.xer"))
        report = compare_schedules(before, after)
        statuses = {change.status for change in report.projects[0].activity_changes}
        self.assertIn("MODIFIED", statuses)
        self.assertTrue(report.projects[0].relationship_changes)
        self.assertFalse(report.projects[0].unresolved_relationships)

    def test_parser_compatibility_retains_empty_positions_and_cp1252(self):
        parsed = XERParser().parse_bytes(("%T\tPROJECT\r\n%F\tproj_id\tproj_name\toptional\r\n%R\tP1\tCaf\xe9\t\r\n%E\r\n").encode("cp1252"))
        raw = parsed.tables["PROJECT"].raw_records[0]
        self.assertEqual(raw.values, ["P1", "Café", ""])
        self.assertIsNone(parsed.tables["PROJECT"].records[0]["optional"])

    def test_report_contract_golden_and_invariants(self):
        golden_path = Path(__file__).parent / "golden" / "empty_report.json"
        golden = json.loads(golden_path.read_text(encoding="utf-8"))
        self.assertEqual(ComparisonReport.model_validate(golden).model_dump(mode="json"), golden)
        report = compare_files(FIXTURES / "compatibility_update_before.xer", FIXTURES / "compatibility_update_after.xer")
        serialized = json.loads(report.model_dump_json())
        self.assertEqual(serialized["schema_version"], "1.0")
        self.assertEqual(json.loads(report.model_dump_json()), json.loads(compare_files(FIXTURES / "compatibility_update_before.xer", FIXTURES / "compatibility_update_after.xer").model_dump_json()))
        for project in report.projects:
            pairs = [(change.before_activity_id, change.after_activity_id)
                     for change in project.activity_changes if change.before_activity_id and change.after_activity_id]
            self.assertEqual(len(pairs), len(set(pairs)))
            for change in project.activity_changes:
                for reference in change.evidence_refs:
                    self.assertIn(reference.evidence_id, report.evidence)
            for relationship in project.relationship_changes:
                for reference in relationship.evidence_refs:
                    self.assertIn(reference.evidence_id, report.evidence)

    def test_unresolved_relationships_are_not_graph_traversable(self):
        project = normalize(XERParser().parse_file(FIXTURES / "compatibility_site.xer")).projects[0]
        unresolved = [relationship for relationship in project.relationships if not relationship.resolved]
        graph = DependencyGraph.from_project(project)
        self.assertTrue(unresolved)
        self.assertTrue(all(relationship.predecessor_id not in graph.immediate_successors(relationship.successor_id)
                            for relationship in unresolved))
