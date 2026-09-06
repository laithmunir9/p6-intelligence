from __future__ import annotations

from pathlib import Path
import unittest

from p6intel.normalize import normalize
from p6intel.parser import XERParser
from p6intel.reconcile import ReconciliationConfig, reconcile


FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str):
    return normalize(XERParser().parse_file(FIXTURES / name)).projects[0]


def project_with_tasks(tasks: list[tuple[str, str, str, str]], relationships: list[tuple[str, str]] | None = None):
    relationships = relationships or []
    lines = ["%T\tPROJECT", "%F\tproj_id\tproj_name", "%R\tP\tTest",
             "%T\tPROJWBS", "%F\twbs_id\tproj_id\twbs_name", "%R\tW\tP\tWork",
             "%T\tTASK", "%F\ttask_id\tproj_id\twbs_id\ttask_name\ttarget_start_date\ttarget_end_date\tremain_drtn_hr_cnt"]
    lines.extend(f"%R\t{task_id}\tP\t{wbs}\t{name}\t{start}\t2026-01-10\t40" for task_id, wbs, name, start in tasks)
    lines.extend(["%T\tTASKPRED", "%F\ttask_id\tpred_task_id\tpred_type"])
    lines.extend(f"%R\t{successor}\t{predecessor}\tPR_FS" for successor, predecessor in relationships)
    lines.append("%E")
    return normalize(XERParser().parse_text("\n".join(lines))).projects[0]


class ReconciliationTests(unittest.TestCase):
    def test_hardening_fixtures_have_varied_structures(self):
        for fixture in ("warehouse.xer", "linear.xer", "program.xer"):
            project = load(fixture)
            self.assertTrue(project.metadata.project_id)
            self.assertTrue(project.activities)
            self.assertTrue(project.wbs)

    def test_every_raw_record_preserves_fields_and_values(self):
        parsed = XERParser().parse_file(FIXTURES / "warehouse.xer")
        for table in parsed.tables.values():
            for raw in table.raw_records:
                self.assertEqual(raw.fields, table.fields)
                self.assertEqual(len(raw.values), len(raw.raw_line.split("\t")) - 1)
                self.assertEqual(raw.raw_line.split("\t")[1:], raw.values)

    def test_fixture_pair_reports_date_relationship_and_activity_changes(self):
        result = reconcile(load("reconcile_before.xer"), load("reconcile_after.xer"))
        by_before = {match["before_activity_id"]: match for match in result.matches}
        self.assertEqual(by_before["A100"]["status"], "UNCHANGED")
        self.assertEqual(by_before["A200"]["status"], "MODIFIED")
        self.assertIn("finish_date", by_before["A200"]["changes"])
        self.assertIn("duration_hours", by_before["A200"]["changes"])
        self.assertIn("wbs_id", by_before["A200"]["changes"])
        self.assertIn("successors", by_before["A200"]["changes"])
        self.assertEqual(by_before["A300"]["status"], "DELETED")
        self.assertEqual(next(m for m in result.matches if m["after_activity_id"] == "A400")["status"], "ADDED")

    def test_source_references_are_present_on_both_sides(self):
        result = reconcile(load("reconcile_before.xer"), load("reconcile_after.xer"))
        modified = next(m for m in result.matches if m["before_activity_id"] == "A200")
        self.assertEqual(modified["before_source_record"]["table"], "TASK")
        self.assertEqual(modified["after_source_record"]["table"], "TASK")

    def test_renamed_activity_is_possible_rename(self):
        before = project_with_tasks([("A1", "W", "Install panels", "2026-01-01")])
        after = project_with_tasks([("B1", "W", "Install solar panels", "2026-01-01")])
        match = reconcile(before, after).matches[0]
        self.assertEqual(match["status"], "POSSIBLE_RENAME")
        self.assertGreater(match["confidence"], 0.78)
        self.assertIn("name", match["changes"])

    def test_ambiguous_rename_is_uncertain(self):
        before = project_with_tasks([("A1", "W", "Install module", "2026-01-01")])
        after = project_with_tasks([("B1", "W", "Install module A", "2026-01-01"),
                                    ("B2", "W", "Install module B", "2026-01-01")])
        match = reconcile(before, after).matches[0]
        self.assertEqual(match["status"], "UNCERTAIN")

    def test_duplicate_names_do_not_force_wrong_wbs_match(self):
        before = project_with_tasks([("A1", "W1", "Repeat", "2026-01-01"), ("A2", "W2", "Repeat", "2026-01-01")])
        after = project_with_tasks([("B1", "W1", "Repeat", "2026-01-01"), ("B2", "W2", "Repeat", "2026-01-01")])
        matches = reconcile(before, after).matches
        self.assertEqual({m["status"] for m in matches}, {"UNCHANGED"})

    def test_exact_id_takes_precedence_over_fuzzy_similarity(self):
        before = project_with_tasks([("A1", "W", "Alpha", "2026-01-01"), ("A2", "W", "Beta", "2026-01-01")])
        after = project_with_tasks([("A1", "W", "Beta", "2026-01-01"), ("B2", "W", "Alpha", "2026-01-01")])
        matches = reconcile(before, after).matches
        exact = next(m for m in matches if m["before_activity_id"] == "A1")
        self.assertEqual(exact["after_activity_id"], "A1")
        self.assertEqual(exact["confidence"], 1.0)

    def test_threshold_is_configurable(self):
        before = project_with_tasks([("A1", "W", "Install panels", "2026-01-01")])
        after = project_with_tasks([("B1", "W", "Install solar panels", "2026-01-01")])
        result = reconcile(before, after, ReconciliationConfig(fuzzy_threshold=0.99))
        self.assertEqual({m["status"] for m in result.matches}, {"ADDED", "DELETED"})


if __name__ == "__main__":
    unittest.main()
