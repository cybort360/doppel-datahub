# Judging map

## Use of DataHub

- Reads live dataset properties, schema metadata, field tags, ownership, and domains through the official Python SDK.
- Uses DataHub context to select generation strategies and preserve declared relationships.
- Writes synthetic assets back with source lineage, tags, expiry, and verification scores.
- Includes a reusable `create-synthetic-data-product` DataHub Skill.

## Technical execution

- Reproducible multi-table generation.
- Gaussian-copula numerical sampling.
- Conditional numerical generation for business relationships such as claim amount by procedure.
- Parent-first foreign-key-safe generation.
- FastAPI API, CLI, Docker image, automated tests, and downloadable evidence bundles.

## Originality

DOPPEL turns catalog context into a new governed data product. It is not another metadata chatbot, incident triage agent, lineage viewer, or code-review guardrail.

## Real-world usefulness

Development, QA, demos, contractor access, and agent testing often need realistic data without distributing production records. DOPPEL provides an explicit review boundary and records the result in the same metadata system teams already use.

## Submission quality

- Under-three-minute demo script.
- One-command fixture mode.
- Public Apache 2.0 repository.
- Sample outputs and machine-readable reports.
- Explicit limits instead of inflated privacy claims.
