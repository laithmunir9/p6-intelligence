# p6intel

An independent engineering prototype for ingesting Primavera P6 XER exports.

Install the package in editable mode, then parse an export:

```bash
python3 -m pip install -e .
python3 -m p6intel parse sample.xer
```

The ingestion layer preserves source scheduling values. The project includes deterministic activity reconciliation and graph impact context, but does not calculate dates, float, or critical path.

Activity reconciliation is available as a separate API:

```python
from p6intel import reconcile

result = reconcile(before_project, after_project)
```

It returns deterministic exact-ID matches first, then conservative WBS/name and configurable fuzzy matches with confidence scores and source-record references.

Milestone 3 adds `DependencyGraph`, `compare_relationships`, and `analyze_impact`. These expose bounded graph context and provenance without recalculating schedule dates, float, or critical path.
