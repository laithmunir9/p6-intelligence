from __future__ import annotations

import json
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

from p6intel.normalize import normalize
from p6intel.parser import XERParser
from p6intel.report import compare_files, compare_schedules


FIXTURES = Path(__file__).parent / "fixtures"


def export(projects: dict[str, list[tuple[str, str]]] , relationships: dict[str, list[tuple[str, str, str, str]]] | None = None):
    relationships = relationships or {}
    lines: list[str] = ["%T\tPROJECT", "%F\tproj_id\tproj_name"]
    lines.extend(f"%R\t{project_id}\tProject {project_id}" for project_id in projects)
    lines += ["%T\tPROJWBS", "%F\twbs_id\tproj_id\twbs_name"]
    lines.extend(f"%R\tW{project_id}\t{project_id}\tWork" for project_id in projects)
    lines += ["%T\tTASK", "%F\ttask_id\tproj_id\twbs_id\ttask_name\ttask_type"]
    for project_id, activities in projects.items():
        lines.extend(f"%R\t{activity_id}\t{project_id}\tW{project_id}\t{name}\tTT_Task" for activity_id, name in activities)
    lines += ["%T\tTASKPRED", "%F\ttask_id\tpred_task_id\tpred_type\tlag_hr_cnt"]
    for project_id in projects:
        lines.extend(f"%R\t{successor}\t{predecessor}\t{relationship_type}\t{lag}"
                     for successor, predecessor, relationship_type, lag in relationships.get(project_id, []))
    lines.append("%E")
    return normalize(XERParser().parse_text("\n".join(lines)))


class ComparisonTests(unittest.TestCase):
    def test_multi_project_added_and_deleted_projects_are_explicit(self):
        before = export({"P1": [("A", "A")], "P2": [("B", "B")]})
        after = export({"P1": [("A", "A")], "P3": [("C", "C")]})
        report = compare_schedules(before, after)
        self.assertEqual([(project.project_id, project.status) for project in report.projects],
                         [("P1", "MATCHED"), ("P2", "DELETED"), ("P3", "ADDED")])
        self.assertEqual({warning.code for project in report.projects for warning in project.warnings},
                         {"PROJECT_ADDED", "PROJECT_DELETED"})

    def test_unresolved_relationships_are_reported_with_evidence(self):
        schedule = export({"P1": [("A", "A")]}, {"P1": [("A", "MISSING", "PR_FS", "-8")]})
        report = compare_schedules(schedule, schedule)
        project = report.projects[0]
        self.assertEqual(len(project.unresolved_relationships), 2)
        self.assertIn("UNRESOLVED_RELATIONSHIP", {warning.code for warning in project.warnings})
        self.assertTrue(project.unresolved_relationships[0].evidence_refs)

    def test_cycles_generate_deterministic_warnings(self):
        schedule = export({"P1": [("A", "A"), ("B", "B")]},
                          {"P1": [("B", "A", "PR_FS", "0"), ("A", "B", "PR_FS", "0")]})
        report = compare_schedules(schedule, schedule)
        self.assertEqual(sum(warning.code == "CYCLE_DETECTED" for warning in report.projects[0].warnings), 2)

    def test_duplicate_relationships_pair_modification_addition_deletion(self):
        before = export({"P1": [("A", "A"), ("B", "B")]},
                        {"P1": [("B", "A", "PR_FS", "0"), ("B", "A", "PR_SS", "0")]})
        changed = export({"P1": [("A", "A"), ("B", "B")]},
                         {"P1": [("B", "A", "PR_FS", "0"), ("B", "A", "PR_SS", "8")]})
        deleted = export({"P1": [("A", "A"), ("B", "B")]},
                         {"P1": [("B", "A", "PR_FS", "0")]})
        added = export({"P1": [("A", "A"), ("B", "B")]},
                       {"P1": [("B", "A", "PR_FS", "0"), ("B", "A", "PR_FF", "0")]})
        self.assertEqual([change.status for change in compare_schedules(before, changed).projects[0].relationship_changes],
                         ["UNCHANGED", "MODIFIED"])
        self.assertEqual([change.status for change in compare_schedules(before, deleted).projects[0].relationship_changes],
                         ["UNCHANGED", "DELETED"])
        self.assertEqual([change.status for change in compare_schedules(deleted, added).projects[0].relationship_changes],
                         ["UNCHANGED", "ADDED"])

    def test_ambiguous_duplicate_pairing_is_explicitly_uncertain(self):
        before = export({"P1": [("A", "A"), ("B", "B")]},
                        {"P1": [("B", "A", "PR_FS", "0"), ("B", "A", "PR_SS", "8")]})
        after = export({"P1": [("A", "A"), ("B", "B")]},
                       {"P1": [("B", "A", "PR_FF", "4")]})
        report = compare_schedules(before, after)
        uncertain = [change for change in report.projects[0].relationship_changes if change.status == "UNCERTAIN"]
        self.assertTrue(uncertain)
        self.assertTrue(uncertain[0].ambiguous)

    def test_output_is_deterministic_and_cli_supports_stdout_and_file(self):
        before_path, after_path = FIXTURES / "reconcile_before.xer", FIXTURES / "reconcile_after.xer"
        first = compare_files(before_path, after_path).model_dump_json()
        second = compare_files(before_path, after_path).model_dump_json()
        self.assertEqual(first, second)
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(Path(__file__).parents[1] / "src")
        command = [sys.executable, "-m", "p6intel", "compare", str(before_path), str(after_path)]
        stdout_result = subprocess.run(command, capture_output=True, text=True, check=True, env=environment)
        self.assertEqual(json.loads(stdout_result.stdout)["schema_version"], "1.1")
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "report.json"
            subprocess.run(command + ["--output", str(output_path)], capture_output=True, text=True, check=True, env=environment)
            self.assertEqual(json.loads(output_path.read_text())["comparison"]["before"]["source_name"], "reconcile_before.xer")

    def test_uncertain_and_traversal_limit_warnings_are_reported(self):
        uncertain_before = export({"P1": [("A", "Install module")]})
        uncertain_after = export({"P1": [("B", "Install module A"), ("C", "Install module B")]})
        uncertain_report = compare_schedules(uncertain_before, uncertain_after)
        self.assertIn("UNCERTAIN_MATCHES", {warning.code for warning in uncertain_report.projects[0].warnings})

        before = export({"P1": [("A", "Start"), ("B", "Finish")]}, {"P1": [("B", "A", "PR_FS", "0")]})
        after = export({"P1": [("A", "Start changed"), ("B", "Finish")]}, {"P1": [("B", "A", "PR_FS", "0")]})
        limited = compare_schedules(before, after, max_traversals=0)
        self.assertIn("TRAVERSAL_LIMIT_REACHED", {warning.code for warning in limited.projects[0].warnings})


if __name__ == "__main__":
    unittest.main()
