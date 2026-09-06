from __future__ import annotations

from pathlib import Path
import unittest

from p6intel.graph import DependencyGraph
from p6intel.impact import analyze_impact, compare_relationships
from p6intel.normalize import normalize
from p6intel.parser import XERParser
from p6intel.reconcile import reconcile, reconcile_exports


FIXTURES = Path(__file__).parent / "fixtures"


def graph_project(task_rows, relationship_rows):
    lines = ["%T\tPROJECT", "%F\tproj_id\tproj_name", "%R\tP\tGraph",
             "%T\tPROJWBS", "%F\twbs_id\tproj_id\twbs_name", "%R\tW\tP\tWork",
             "%T\tTASK", "%F\ttask_id\tproj_id\twbs_id\ttask_name\ttask_type\ttarget_start_date\ttarget_end_date\ttotal_float_hr_cnt\tcritical_flag"]
    lines.extend(f"%R\t{task_id}\tP\tW\t{name}\t{task_type}\t2026-01-01\t2026-01-02\t{float_hours}\t{critical}"
                 for task_id, name, task_type, float_hours, critical in task_rows)
    lines.extend(["%T\tTASKPRED", "%F\ttask_id\tpred_task_id\tpred_type\tlag_hr_cnt"])
    lines.extend(f"%R\t{successor}\t{predecessor}\t{relationship_type}\t{lag}"
                 for successor, predecessor, relationship_type, lag in relationship_rows)
    lines.append("%E")
    return normalize(XERParser().parse_text("\n".join(lines))).projects[0]


class GraphImpactTests(unittest.TestCase):
    def test_relationship_types_and_lags_are_preserved(self):
        project = graph_project([("A", "A", "TT_Task", "0", "N"), ("B", "B", "TT_Task", "1", "N"),
                                 ("C", "C", "TT_Task", "2", "N"), ("D", "D", "TT_Task", "3", "N"),
                                 ("E", "E", "TT_Mile", "4", "Y")],
                                [("B", "A", "PR_FS", "0"), ("C", "A", "PR_SS", "-8"),
                                 ("D", "B", "PR_FF", "4"), ("E", "D", "PR_SF", "12")])
        graph = DependencyGraph.from_project(project)
        self.assertEqual([(edge.relationship_type, edge.lag_hours) for edge in graph.edges],
                         [("FS", "0"), ("SS", "-8"), ("FF", "4"), ("SF", "12")])
        self.assertEqual(graph.nodes["E"].is_milestone, True)

    def test_branching_converging_queries_and_milestone_paths(self):
        project = graph_project([("A", "Start", "TT_Task", "0", "N"), ("B", "Branch one", "TT_Task", "0", "N"),
                                 ("C", "Branch two", "TT_Task", "0", "N"), ("D", "Converge", "TT_Task", "0", "N"),
                                 ("M", "Finish", "TT_Mile", "0", "N")],
                                [("B", "A", "PR_FS", "0"), ("C", "A", "PR_FS", "0"),
                                 ("D", "B", "PR_FS", "0"), ("D", "C", "PR_FS", "0"), ("M", "D", "PR_FS", "0")])
        graph = DependencyGraph.from_project(project)
        self.assertEqual(graph.immediate_successors("A"), ["B", "C"])
        self.assertEqual(graph.immediate_predecessors("D"), ["B", "C"])
        self.assertEqual(set(graph.downstream("A").activities), {"B", "C", "D", "M"})
        self.assertEqual(set(graph.upstream("M").activities), {"A", "B", "C", "D"})
        self.assertIn(["A", "B", "D", "M"], graph.paths("A", "M"))
        self.assertEqual(graph.paths_to_milestones("A"), [["A", "B", "D", "M"], ["A", "C", "D", "M"]])

    def test_cycles_are_reported_and_disconnected_components_are_safe(self):
        project = graph_project([("A", "A", "TT_Task", "0", "N"), ("B", "B", "TT_Task", "0", "N"),
                                 ("C", "C", "TT_Task", "0", "N"), ("X", "X", "TT_Task", "0", "N")],
                                [("B", "A", "PR_FS", "0"), ("A", "B", "PR_FS", "0"), ("C", "X", "PR_FS", "0")])
        graph = DependencyGraph.from_project(project, max_traversals=10)
        self.assertTrue(graph.cycles())
        self.assertTrue(graph.downstream("A").cycles)
        self.assertEqual(graph.connected_components(), [["A", "B"], ["C", "X"]])

    def test_relationship_comparison_classifies_added_deleted_and_modified(self):
        before = graph_project([("A", "A", "TT_Task", "0", "N"), ("B", "B", "TT_Task", "0", "N"),
                                ("C", "C", "TT_Task", "0", "N")],
                               [("B", "A", "PR_FS", "0"), ("C", "B", "PR_FS", "0")])
        after = graph_project([("A", "A", "TT_Task", "0", "N"), ("B", "B", "TT_Task", "0", "N"),
                               ("C", "C", "TT_Task", "0", "N"), ("D", "D", "TT_Task", "0", "N")],
                              [("B", "A", "PR_SS", "8"), ("D", "B", "PR_FS", "0")])
        result = reconcile(before, after)
        statuses = [change.status for change in compare_relationships(before, after, result)]
        self.assertEqual(statuses, ["MODIFIED", "DELETED", "ADDED"])

    def test_changed_activity_id_uses_reconciled_identity_and_impact_provenance(self):
        before = graph_project([("A", "Start", "TT_Task", "0", "N"), ("M", "Finish", "TT_Mile", "0", "N")],
                               [("M", "A", "PR_FS", "0")])
        after = graph_project([("B", "Start renamed", "TT_Task", "0", "N"), ("M", "Finish", "TT_Mile", "0", "N")],
                              [("M", "B", "PR_FS", "0")])
        reconciliation = reconcile(before, after)
        self.assertEqual(next(match for match in reconciliation.matches if match["before_activity_id"] == "A")["status"], "POSSIBLE_RENAME")
        impact = analyze_impact(before, after, reconciliation)
        self.assertEqual(impact.impacts[0]["source_activity"], "B")
        self.assertEqual(impact.impacts[0]["downstream_milestones"], ["M"])
        self.assertEqual(impact.impacts[0]["paths"], [["B", "M"]])
        self.assertEqual(impact.impacts[0]["source_record"]["table"], "TASK")
        self.assertEqual(len(impact.impacts[0]["path_evidence"][0]["edge_source_records"]), 1)
        self.assertEqual(impact.impacts[0]["path_evidence"][0]["edge_source_records"][0]["table"], "TASKPRED")
        self.assertEqual(impact.relationship_changes[0].status, "UNCHANGED")

    def test_uncertain_matches_are_reported_and_excluded_from_impact(self):
        before = graph_project([("A", "Install module", "TT_Task", "0", "N")], [])
        after = graph_project([("B", "Install module A", "TT_Task", "0", "N"),
                               ("C", "Install module B", "TT_Task", "0", "N")], [])
        reconciliation = reconcile(before, after)
        impact = analyze_impact(before, after, reconciliation)
        self.assertEqual(len(impact.uncertain_matches), 1)
        self.assertEqual(impact.impacts, [])
        self.assertTrue(impact.model_dump()["uncertain_matches"])

    def test_multi_project_orchestration(self):
        before = normalize(XERParser().parse_file(FIXTURES / "sample.xer"))
        after = normalize(XERParser().parse_file(FIXTURES / "sample.xer"))
        result = reconcile_exports(before, after)
        self.assertEqual([project.project_id for project in result.projects], ["P1", "P2"])
        self.assertEqual(result.uncertain_matches, [])


if __name__ == "__main__":
    unittest.main()
