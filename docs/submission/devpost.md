# DOPPEL — Devpost submission

## One-line pitch

DOPPEL reads DataHub-governed metadata for a sensitive dataset, generates a privacy-safe synthetic twin, proves it is safe and useful, then writes the twin back into DataHub with lineage, scores, and evidence.

## Try it out

- **Live demo:** https://doppel-datahub.vercel.app
- **Source code:** https://github.com/cybort360/doppel-datahub

## Inspiration

Product teams, contractors, and agents constantly need realistic data to build and test against. The source data usually contains direct identifiers, protected health information, financial records, or other restricted attributes. Handing over production rows exposes the organization; handing over naive fake rows breaks application logic because keys, distributions, correlations, and relationships no longer match.

We wanted a tool that treats the data catalog — DataHub — as the source of truth for governance, so the synthetic twin inherits the same schemas, tags, owners, domains, and lineage as the source. If the catalog says a column is PII, the twin must never expose it. If the catalog declares a foreign key, the twin must honor it. If the catalog records an owner, the twin must carry that owner forward.

## What it does

DOPPEL is a metadata-aware synthetic data product generator.

1. **Reads catalog context** — schema, primary/foreign keys, tags, glossary terms, ownership, domains, and lineage from DataHub (or a checked-in fixture).
2. **Plans generation** — assigns a typed strategy to every column based on semantic type and governance tags.
3. **Generates linked tables** — parent tables first, surrogate identifiers, distribution-preserving dates, categorical and numeric modelling, and relationship-preserving foreign keys.
4. **Verifies fail-closed** — exact-row overlap, direct-identifier overlap, singling-out risk, distribution similarity, correlations, conditional relationships, aggregate-query similarity, and referential integrity.
5. **Writes back to DataHub** — registers the synthetic datasets with `SYNTHETIC` and `NON_PRODUCTION` tags, source lineage, owner/domain, scores, timestamps, expiry, and a linked evidence report.

The healthcare demo turns ~1,200 patients and ~4,200 encounters into a VERIFIED development twin with zero copied rows, zero leaked identifiers, and ~98.7% utility.

## How we built it

- **Backend:** FastAPI + Pydantic, pandas/numpy/scipy for generation and verification, Faker for direct identifiers, `acryl-datahub` for catalog read/write.
- **Frontend:** Plain HTML/CSS/JS dashboard that consumes the SSE `/api/runs/stream` endpoint so progress reflects real backend stages.
- **Generation engine:** Deterministic, seeded multi-table synthesizer with surrogate IDs, empirical quantile sampling, Gaussian copula for correlated numerics, and FK-safe parent-first generation.
- **Verification:** Lightweight deterministic metrics — KS/TVD for distributions, Pearson correlation similarity, grouped-mean preservation, joint-distribution relationships, and cardinality shape comparison.
- **DataHub integration:** Reads `SchemaMetadata`, `GlobalTags`, `GlossaryTerms`, `Ownership`, `Domains`, and `UpstreamLineage`; writes `DatasetProperties`, `GlobalTags`, `UpstreamLineage`, `SchemaMetadata`, and `InstitutionalMemory` evidence.
- **DataHub Skill:** A reusable, upstream-ready skill contribution in `skills/create-synthetic-data-product/` that teaches any compatible agent the same fail-closed workflow.

## Challenges

- **Real catalog schema is messy.** Field type classes, tag/term URNs, and foreign-key references differ between fixture data and a live DataHub GMS. We had to make enrichment tolerant of missing aspects while still using the catalog when it is present.
- **Determinism vs. realism.** Jittering dates and adding noise makes data realistic, but using wall-clock time for clamping or age calculations would break reproducibility. We fixed reference dates to source-derived values so the same seed always produces the same output.
- **Fail-closed verification without formal privacy proofs.** We deliberately do not claim differential privacy. Instead we prove the negative cases that matter most for engineering use: no full row copies, no direct identifier leakage, valid foreign keys, and bounded distribution drift.
- **DataHub writeback idempotency.** Re-running the pipeline must not create duplicate datasets or lineage edges. DataHub aspect overwrites make this work, but we still validate it in integration tests.

## Accomplishments

- End-to-end live DataHub path exercised: bootstrap source datasets, read metadata, generate, verify, publish, inspect lineage, and download evidence.
- Deterministic output verified: same seed + same input yields identical rows; different seeds yield disjoint identifiers.
- Privacy gates proven: zero exact-row overlap and zero direct-identifier overlap on the full healthcare dataset.
- Referential integrity proven: all encounter `patient_id` values resolve to a generated patient.
- Clean-clone test passed from a fresh virtual environment using only the README instructions.
- Reusable DataHub Skill prepared for upstream contribution.

## What we learned

- Metadata-first generation is far more robust than hand-coded column lists. When DataHub is the source of truth, changing a tag or adding a column automatically changes the twin.
- Fail-closed verification is a product feature, not an afterthought. Judges and reviewers need to see the proof, not just a score.
- Synthetic data tools must be honest about what they guarantee. We explicitly label the checks as heuristics and tag outputs `NON_PRODUCTION`.
- DataHub's aspect model makes idempotent writeback straightforward once you treat every write as an upsert.

## What's next

- Optional differential-privacy or k-anonymity modes for stricter guarantees.
- Connectors beyond CSV, starting with SQLAlchemy/PostgreSQL and BigQuery.
- Row-level access control and audit logging for artifact downloads.
- Multi-agent review workflow separating generation, verification, and approval.
- Integration with DataHub assertions and quality signals to drive generation parameters.

## Built with

- Python 3.12
- FastAPI + Pydantic + Pydantic Settings
- pandas, numpy, scipy, Faker
- DataHub (`acryl-datahub` Python SDK + REST emitter)
- HTML/CSS/JS dashboard
- Docker + Docker Compose
- Vercel (serverless deployment of the live demo)
- pytest, ruff, mypy
