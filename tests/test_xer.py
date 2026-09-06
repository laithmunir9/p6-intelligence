from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
import unittest

from p6intel.normalize import normalize
from p6intel.parser import XERParser


SAMPLE = """\\
%T\tPROJECT
%F\tproj_id\tproj_short_name\tproj_name\tplan_start_date\tplan_end_date\tclndr_id
%R\tP1\tDEMO\tDemo Project\t2026-01-01\t2026-03-01\tC1
%R\tP2\tSECOND\tSecond Project\t2026-02-01\t2026-04-01\tC1
%T\tPROJWBS
%F\twbs_id\tproj_id\tparent_wbs_id\twbs_short_name\twbs_name
%R\tW1\tP1\t\tROOT\tRoot
%R\tW2\tP1\tW1\tPKG\tPackage
%T\tTASK
%F\ttask_id\tproj_id\twbs_id\ttask_code\ttask_name\ttarget_start_date\ttarget_end_date\tcustom_field
%R\tA1\tP1\tW2\tA-1\tFirst\t2026-01-01\t2026-01-05\tkept
%R\tA2\tP1\tW2\tA-2\tSecond\t2026-01-06\t2026-01-10\t
%T\tTASKPRED
%F\ttask_id\tpred_task_id\tpred_type\tlag_hr_cnt
%R\tA2\tA1\tPR_FS\t0
%R\tA1\tMISSING\tPR_FS\t8
%T\tCALENDAR
%F\tclndr_id\tclndr_name\tclndr_type\tdefault_flag
%R\tC1\tStandard\tPROJECT\tY
%T\tVENDOR_TABLE
%F\tfoo\tbar
%R\tx\ty
%E
""".lstrip("\\")


class XERTests(unittest.TestCase):
    def test_normal_file_normalizes_and_resolves_relationships(self):
        parsed = XERParser().parse_text(SAMPLE)
        result = normalize(parsed)
        self.assertEqual(len(result.projects), 2)
        project = result.projects[0]
        self.assertEqual(project.metadata.name, "Demo Project")
        self.assertEqual(project.wbs[0].children[0].name, "Package")
        self.assertEqual(project.activities[0].target_start, "2026-01-01")
        self.assertTrue(project.relationships[0].resolved)
        self.assertEqual(project.relationships[0].predecessor.activity_id, "A1")
        self.assertIn("VENDOR_TABLE", result.unknown_tables)

    def test_missing_values_become_none(self):
        parsed = XERParser().parse_text("%T\tTASK\n%F\ttask_id\ttask_name\n%R\tA1\t\n")
        row = parsed.tables["TASK"].records[0]
        self.assertIsNone(row["task_name"])

    def test_unknown_fields_are_preserved_in_raw_and_typed_models(self):
        parsed = XERParser().parse_text("%T\tTASK\n%F\ttask_id\tfuture_col\n%R\tA1\tvalue\n")
        row = parsed.tables["TASK"].records[0]
        self.assertEqual(row["future_col"], "value")
        normalized = normalize(parsed)
        self.assertEqual(normalized.projects[0].activities[0].future_col, "value")

    def test_malformed_records_are_diagnosed_without_crashing(self):
        parsed = XERParser().parse_text("%R\tnope\n%T\n%T\tTASK\n%F\ttask_id\ttask_name\n%R\tA1\nplain garbage\n")
        self.assertEqual(len(parsed.tables["TASK"].records), 1)
        self.assertGreaterEqual(len(parsed.diagnostics), 3)

    def test_unresolved_relationship_is_retained(self):
        parsed = XERParser().parse_text("%T\tTASKPRED\n%F\ttask_id\tpred_task_id\n%R\tA2\tA1\n")
        relationship = normalize(parsed).projects[0].relationships[0]
        self.assertFalse(relationship.resolved)
        self.assertEqual(relationship.predecessor_id, "A1")
        self.assertIsNone(relationship.predecessor)

    def test_encoding_fallback(self):
        parsed = XERParser().parse_bytes("%T\tPROJECT\n%F\tproj_name\n%R\tCafé\n".encode("cp1252"))
        self.assertEqual(parsed.tables["PROJECT"].records[0]["proj_name"], "Café")

    def test_cli_outputs_json(self):
        fixture = Path(__file__).parent / "fixtures" / "sample.xer"
        import os
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(Path(__file__).parents[1] / "src")
        completed = subprocess.run([sys.executable, "-m", "p6intel", "parse", str(fixture)], capture_output=True, text=True, check=True, env=environment)
        payload = json.loads(completed.stdout)
        self.assertEqual(len(payload["projects"]), 2)


if __name__ == "__main__":
    unittest.main()
