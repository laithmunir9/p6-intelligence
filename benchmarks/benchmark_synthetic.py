"""Lightweight scale sanity check; timings are informational, not thresholds."""

from __future__ import annotations

import time

from p6intel.graph import DependencyGraph
from p6intel.normalize import normalize
from p6intel.parser import XERParser
from p6intel.report import compare_schedules


def make_xer(activity_count: int = 1000) -> bytes:
    lines = ["%T\tPROJECT", "%F\tproj_id\tproj_name", "%R\tBENCH\tBenchmark",
             "%T\tPROJWBS", "%F\twbs_id\tproj_id\twbs_name", "%R\tW\tBENCH\tWork",
             "%T\tTASK", "%F\ttask_id\tproj_id\twbs_id\ttask_name\ttask_type"]
    lines.extend(f"%R\tA{i}\tBENCH\tW\tActivity {i}\tTT_Task" for i in range(activity_count))
    lines += ["%T\tTASKPRED", "%F\ttask_id\tpred_task_id\tpred_type\tlag_hr_cnt"]
    lines.extend(f"%R\tA{i}\tA{i - offset}\tPR_FS\t0"
                 for offset in (1, 2, 3) for i in range(offset, activity_count))
    lines.append("%E")
    return ("\n".join(lines) + "\n").encode("utf-8")


def main() -> None:
    raw = make_xer()
    timings = {}
    start = time.perf_counter(); parsed = XERParser().parse_bytes(raw); timings["parse_seconds"] = time.perf_counter() - start
    start = time.perf_counter(); before = normalize(parsed); timings["normalize_seconds"] = time.perf_counter() - start
    start = time.perf_counter(); graph = DependencyGraph.from_project(before.projects[0]); timings["graph_seconds"] = time.perf_counter() - start
    start = time.perf_counter(); compare_schedules(before, before); timings["reconcile_report_seconds"] = time.perf_counter() - start
    print({"activities": len(graph.nodes), "relationships": len(graph.edges), **timings})


if __name__ == "__main__":
    main()
