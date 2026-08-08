---
name: create-synthetic-data-product
description: Generate a governed synthetic data product from a DataHub asset. Resolves source metadata, builds a per-column generation strategy, produces privacy-safe synthetic data, verifies privacy/utility/integrity, fails closed when unsafe, and registers the twin in DataHub with lineage and evidence.
license: Apache-2.0
user-invocable: true
effort: high
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob
---

# Create a governed synthetic data product

Use this skill when a user needs a useful development or testing copy of a sensitive, restricted, or production DataHub dataset, and wants the result registered as a governed catalog asset with source lineage and verification evidence.

## Multi-agent compatibility

This skill works across Claude Code, Cursor, Codex, Copilot, Gemini CLI, Windsurf, and other Agent Skills-compatible tools.

**What works everywhere:**

- The full ten-step workflow below.
- Reading DataHub metadata via the DataHub CLI (`datahub get`) or Python SDK.
- Generating synthetic data with deterministic, seeded engines.
- Running privacy/utility/integrity checks.
- Writing assets, tags, lineage, and evidence back to DataHub.

**Claude Code-specific features** (other agents can ignore):

- `allowed-tools` and `hooks` in the YAML frontmatter.
- `Task(subagent_type="...")` for delegated verification — fallback instructions are provided inline.

## Required loop

Execute these steps in order. Do not skip a step because the source "looks simple."

### 1. Resolve the source asset

Do not generate from an ambiguous table name. Obtain the full DataHub URN or resolve it with `datahub get` / `datahub search`.

Required inputs:

- Source dataset URN(s).
- Whether the asset is a single table or a set of related tables.
- The intended scale factor, seed, expiry, and target environment.

### 2. Inspect schema, governance, and lineage

Read these aspects for every source table:

- `datasetProperties` — name, description, custom properties.
- `schemaMetadata` — fields, native types, nullability, `primaryKeys`, `foreignKeys`.
- `globalTags` — `PII`, `PHI`, `RESTRICTED`, `QUASI_IDENTIFIER`, `FINANCIAL`, etc.
- `glossaryTerms` — semantic hints (e.g., `Person Name`, `Email Address`).
- `ownership` — owner to carry forward.
- `domains` — domain to carry forward.
- `upstreamLineage` — existing upstreams to preserve in the synthetic twin's lineage.

### 3. Identify sensitive columns

Classify every column into one of these categories:

| Category | Examples | Handling |
|---|---|---|
| Direct identifier | `patient_id`, `ssn`, `email`, `first_name`, `last_name`, `phone`, `address`, `postal_code` | Replace with synthetic surrogate or faker value; never copy source values. |
| Quasi-identifier | `date_of_birth`, `postal_code`, `sex` tagged `QUASI_IDENTIFIER` | Generalize or jitter; measure singling-out risk. |
| Sensitive attribute | `diagnosis_code`, `procedure_code`, `claim_amount` | Preserve statistical distribution; do not copy individual values. |
| Foreign key | `patient_id` in child table | Remap to new synthetic parent keys while preserving relationship shape. |
| Non-sensitive numeric/categorical | `visits_last_year`, `facility`, `status` | Preserve empirical distribution. |

### 4. Build a typed generation plan

Before generating any rows, produce a plan document (`GENERATION_PLAN.md`) that lists every column and its strategy. Example strategies:

- `surrogate_id` — non-colliding synthetic primary key.
- `faker_name` — synthetic person name.
- `reserved_domain_email` — synthetic email in a reserved domain.
- `distribution_preserving_date` — date with bounded jitter.
- `categorical_distribution` — empirical PMF sampling.
- `gaussian_copula` — multivariate numeric sampling.
- `conditional_on:<column>` — numeric value conditioned on a group column.
- `frequency_preserving_fk` — foreign key that reproduces the parent-child cardinality shape.

### 5. Execute synthetic generation

Generate parent tables before child tables. For each table:

1. Generate primary keys first.
2. Generate direct-identifier columns with dedicated generators.
3. Generate quasi-identifiers with generalization/jitter.
4. Generate numeric/categorical columns preserving distributions.
5. Generate foreign keys last, mapping to the new synthetic parent keys.

Use a fixed seed so the run is reproducible.

### 6. Run privacy verification

Calculate and record:

- `exact_row_overlap` — count of complete source rows reproduced in the synthetic output. Must be `0`.
- `direct_identifier_overlap` — count of source identifier values appearing in the synthetic output. Must be `0`.
- `singling_out_rate` — fraction of synthetic rows in small quasi-identifier groups. Report and flag if high.

If either overlap is greater than `0`, stop and mark the run `REJECTED`.

### 7. Run utility verification

Calculate:

- `schema_match` — column names/order preserved.
- `mean_null_rate_delta` — delta in null rates.
- Per-column distribution similarity (KS for numeric/date, TVD for categorical).
- `correlation_similarity` — pairwise numeric correlations.
- `conditional_relationship_similarity` — grouped means preserved.
- `aggregate_query_similarity` — representative queries produce similar results.
- `cardinality_similarity` — children-per-parent shape preserved.

Document thresholds. A `VERIFIED` twin must clear them.

### 8. Run integrity verification

For every declared foreign key:

- Count orphan child values with no matching synthetic parent. Must be `0`.
- Measure cardinality shape preservation.

If any foreign key is broken, mark the run `REJECTED`.

### 9. Fail closed or publish

A run may only be marked `VERIFIED` when **all** of the following are true:

- `exact_row_overlap == 0`
- `direct_identifier_overlap == 0`
- Privacy score is `100.0`
- Integrity score is `100.0`
- Utility score clears the documented threshold (e.g., `>= 70.0`)
- No privacy, integrity, or utility metric reports `fail`

If any gate fails, produce a `REJECTED` report with explicit reasons. Do **not** publish to DataHub.

If `VERIFIED`, publish the synthetic datasets to DataHub with:

- `SYNTHETIC` and `NON_PRODUCTION` tags.
- Upstream lineage to the source dataset(s).
- Owner and domain inherited from the source.
- Custom properties: `privacy_score`, `utility_score`, `integrity_score`, `generated_at`, `expires_at`, `doppel_run_id`, `source_dataset`, `source_asset`.
- `InstitutionalMemory` evidence report linked to each synthetic asset.

### 10. Write evidence back into DataHub

Attach a durable evidence report that includes:

- Full privacy, utility, and integrity metrics.
- The generation plan.
- Decision (`VERIFIED` or `REJECTED`) and reasons.
- A clear statement that the checks are heuristics, not differential privacy or legal anonymization.

## Output contract

Produce a machine-readable report with this shape:

```json
{
  "source_urn": "urn:li:dataset:(...)",
  "synthetic_urns": ["urn:li:dataset:(...)"],
  "decision": "VERIFIED | REJECTED",
  "reasons": ["..."],
  "privacy": {
    "exact_row_overlap": 0,
    "direct_identifier_overlap": 0,
    "singling_out_rate": 0.0,
    "formal_dp_guarantee": false
  },
  "utility": {
    "schema_match": 1.0,
    "mean_distribution_similarity": 0.0,
    "correlation_similarity": 0.0,
    "conditional_similarity": 0.0
  },
  "integrity": {
    "fk_integrity": 1.0,
    "orphan_foreign_keys": 0
  },
  "governance": {
    "environment": "NON_PROD",
    "tags": ["SYNTHETIC", "NON_PRODUCTION"],
    "expires_at": "ISO-8601 timestamp"
  }
}
```

## Refusal conditions

Do not publish the output when:

- Any direct identifier from the source appears in the synthetic data.
- Any full source row is reproduced.
- A declared foreign key relationship is broken.
- The output is being represented as anonymous, anonymized, or legally compliant without an appropriate formal assessment.
- The destination is production and the use case has not been explicitly reviewed.
- The source asset is unidentified or the user refuses to provide a DataHub URN.

## Templates

Read `templates/generation-plan.template.md` before creating the plan.

Read `templates/evidence-report.template.md` before writing the final report.

## References

| Document | Purpose |
|---|---|
| `references/sensitive-column-checklist.md` | How to classify columns from tags, terms, and names |
| `references/verification-thresholds.md` | Default thresholds and what they mean |
| `references/datahub-aspects-used.md` | Aspects to read and write |

## Remember

1. **Metadata first.** Never generate before reading schema, tags, keys, and lineage.
2. **Typed strategies.** Every column must have an explicit generation strategy.
3. **Parents first.** Generate parent tables before children to keep foreign keys valid.
4. **Fail closed.** When in doubt, reject the run.
5. **Evidence is required.** A published twin must carry scores, expiry, lineage, and a limitation statement.
6. **Do not overclaim.** Heuristic privacy checks are not differential privacy.
