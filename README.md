# P6 Intelligence

An independent engineering prototype for ingesting Primavera P6 XER exports and comparing schedule updates with deterministic, source-traceable results.

## Live demo

[Open the hosted comparison demo](https://p6-intelligence.vercel.app). Select **Try synthetic demo** to compare a redistribution-safe substation expansion scenario, or upload two of your own XER exports. The demo uses the same read-only comparison API as custom uploads.

## Why it exists

Schedule updates are often reviewed as isolated activity changes. P6 Intelligence keeps exported schedule values intact, identifies activity and relationship changes, traces bounded dependency context, and links conclusions back to exact source records. Ambiguous matches and unresolved references remain visible instead of being silently forced.

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

The package is separated into parser, normalization, reconciliation, graph, impact, report, and API layers. `compare_schedules()` composes those deterministic services into a versioned `ComparisonReport`; `compare_files()` is the thin filesystem wrapper.

```text
XER exports ──> parser ──> normalized project model ──> reconciliation
                                                       │
                                                       ├─> dependency graph / impact
                                                       └─> evidence-backed report ──> API / web demo
```

The XER parser preserves unknown tables, fields, positional values, and source lines. Normalized activities and relationships retain source records. The report layer deduplicates those records in an evidence registry and exposes stable evidence references.

Report schema version `1.1` is centralized in `p6intel.report.models`. Version 1.1 adds compact server-provided activity metadata and path references; the existing activity IDs, path arrays, and evidence references remain available.

## Uncertainty and scope

Exact activity IDs take precedence over fuzzy reconciliation. Ambiguous activity or duplicate-relationship matches are reported as uncertain rather than silently forced. Unresolved relationships, cycles, and traversal limits become machine-readable warnings.

The system preserves P6-exported dates, durations, float, critical flags, relationship types, and lag values. It does not recalculate dates, float, critical path, longest path, or schedule causality. It does not modify P6 schedules. There is no AI layer, database, authentication, or persistence.

Known limitations include conservative project-ID matching, unresolved edges being excluded from graph traversal, and limited automatic pairing of ambiguous duplicate relationships.

## Read-only API

Run locally with:

```bash
uvicorn p6intel.api.app:app --reload
```

Endpoints:

- `GET /health` returns service and report-schema status.
- `POST /v1/compare` accepts `before` and `after` XER files as multipart uploads and returns the canonical `ComparisonReport` JSON.

The default per-file upload limit is 50 MiB. Set `P6INTEL_MAX_UPLOAD_MB` to change it. CORS is disabled unless `P6INTEL_CORS_ORIGINS` is set to a comma-separated allowlist of origins; wildcard CORS is not enabled by default.

## Prototype deployment

The read-only API is deployed at `https://p6-intelligence.onrender.com`.

```bash
curl https://p6-intelligence.onrender.com/health
curl -X POST https://p6-intelligence.onrender.com/v1/compare \
  -F before=@before.xer \
  -F after=@after.xer
```

The public prototype uses one Uvicorn process and limits each uploaded XER file to 25 MiB. Large comparisons may consume significant CPU and memory.

The live frontend is available at `https://p6-intelligence.vercel.app` and uses the API at `https://p6-intelligence.onrender.com`.

Activity reconciliation is available as a separate API:

```python
from p6intel import reconcile

result = reconcile(before_project, after_project)
```

It returns deterministic exact-ID matches first, then conservative WBS/name and configurable fuzzy matches with confidence scores and source-record references.

`DependencyGraph`, `compare_relationships`, and `analyze_impact` expose bounded graph context and provenance without recalculating schedule dates, float, or critical path.

## Local frontend

The read-only comparison frontend lives in `web/`.

```bash
cd web
npm install
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 npm run dev
```

`NEXT_PUBLIC_API_BASE_URL` selects the backend used by the browser. It defaults to `http://localhost:8000` for local development.
