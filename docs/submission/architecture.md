# DOPPEL architecture

```text
DataHub GMS / fixture context
        │
        ▼
┌─────────────────┐
│ CatalogService  │── schema, tags, terms, ownership, domains, lineage
└─────────────────┘
        │
        ▼
┌───────────────────┐
│ SyntheticGenerator│── surrogate IDs, categorical/numeric/date generation,
│                   │   FK-safe multi-table output
└───────────────────┘
        │
        ▼
┌─────────────────┐
│   Evaluation    │── privacy + utility + integrity gates
└─────────────────┘
        │
        ├─► CSV + report.json + README + ZIP bundle
        │
        ▼
┌─────────────────┐
│ DataHubPublisher│── tags, lineage, properties, evidence
└─────────────────┘
```

## Components

### `app/services/catalog.py`

- Loads dataset context from `data/healthcare/context.json` in fixture mode.
- In live mode, connects to DataHub GMS and reads `DatasetProperties`, `SchemaMetadata`, `GlobalTags`, `GlossaryTerms`, `Ownership`, `Domains`, and `UpstreamLineage`.
- Infers semantic types from native types, column names, tags, and glossary terms.
- Produces a typed generation plan per column.

### `app/services/synthesizer.py`

- Seeded, deterministic generator.
- Generates parent tables before children to keep foreign keys resolvable.
- Strategies include surrogate IDs, Faker-based names/emails/postcodes, empirical categorical sampling, date jitter, Gaussian-copula numerics, and conditional numeric sampling.
- Builds a source-key → synthetic-key map so child tables reference the new parent keys while preserving cardinality shape.

### `app/services/evaluation.py`

- Privacy: exact-row SHA-256 overlap, direct-identifier set intersection, quasi-identifier singling-out rate.
- Utility: schema match, null-rate delta, KS/TVD distribution similarity, correlation similarity, conditional mean similarity, aggregate-query similarity, relationship joint distributions, cardinality shape similarity.
- Integrity: orphan foreign keys and children-per-parent shape preservation.
- Fail-closed `render_decision()` requires privacy=100, integrity=100, utility≥70, zero overlaps, and no failed metric.

### `app/services/datahub.py`

- Fixture mode writes a JSON mutation preview to the run artifact.
- Live mode emits `DatasetProperties`, `GlobalTags`, `UpstreamLineage`, `SchemaMetadata`, and `InstitutionalMemory` aspects for each synthetic dataset.
- Uses aspect overwrites for idempotency.

### `app/main.py`

- FastAPI application serving health, asset, run, download, and SSE streaming endpoints.
- Static dashboard mounted at `/`.

### `app/static/`

- Browser dashboard: Data Asset → Generation Plan → Live Pipeline → Verification → DataHub Writeback.
- Uses Server-Sent Events from `/api/runs/stream` to show real backend progress.
