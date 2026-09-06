# p6intel

An independent engineering prototype for ingesting and comparing Primavera P6 XER exports.

Install the package in editable mode:

```bash
python3 -m pip install -e .
```

Parse one export:

```bash
python3 -m p6intel parse sample.xer
```

Compare two exports:

```bash
python3 -m p6intel compare before.xer after.xer
python3 -m p6intel compare before.xer after.xer --output report.json
```

## Architecture

The package is separated into parser, normalization, reconciliation, graph, impact, and report layers. `compare_schedules()` composes those deterministic services into a versioned `ComparisonReport`; `compare_files()` is the thin filesystem wrapper.

The XER parser preserves unknown tables, fields, positional values, and source lines. Normalized activities and relationships retain source records. The report layer deduplicates those records in an evidence registry and exposes stable evidence references.

Report schema version `1.0` is centralized in `p6intel.report.models`.

## Uncertainty and scope

Exact activity IDs take precedence over fuzzy reconciliation. Ambiguous activity or duplicate-relationship matches are reported as uncertain rather than silently forced. Unresolved relationships, cycles, and traversal limits become machine-readable warnings.

The system preserves P6-exported dates, durations, float, critical flags, relationship types, and lag values. It does not recalculate dates, float, critical path, longest path, or schedule causality. It does not modify P6 schedules and contains no frontend, AI, database, authentication, or deployment layer.

Known limitations include conservative project-ID matching, unresolved edges being excluded from graph traversal, and limited automatic pairing of ambiguous duplicate relationships.

Activity reconciliation is available as a separate API:

```python
from p6intel import reconcile

result = reconcile(before_project, after_project)
```

It returns deterministic exact-ID matches first, then conservative WBS/name and configurable fuzzy matches with confidence scores and source-record references.

Milestone 3 adds `DependencyGraph`, `compare_relationships`, and `analyze_impact`. These expose bounded graph context and provenance without recalculating schedule dates, float, or critical path.
