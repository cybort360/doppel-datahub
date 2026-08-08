# DOPPEL Evidence Report

## Run summary

- **Run ID:** `{run_id}`
- **Source asset:** `{source_urn}`
- **Decision:** `VERIFIED | REJECTED`
- **Generated at:** `{generated_at}`
- **Expires at:** `{expires_at}`

## Decision reasons

- `{reason}`

## Privacy

| Metric | Value | Threshold | Status |
|---|---|---|---|
| Exact row overlap | `{value}` | `0` | `{pass/fail}` |
| Direct identifier overlap | `{value}` | `0` | `{pass/fail}` |
| Singling-out rate | `{value}` | `< 10%` | `{pass/warn/fail}` |

**Privacy score:** `{privacy_score}`

## Utility

| Metric | Value | Status |
|---|---|---|
| Schema match | `{value}` | `{pass/fail}` |
| Mean null-rate delta | `{value}` | `{pass/warn/fail}` |
| Distribution similarity | `{value}` | `{pass/warn/fail}` |
| Correlation similarity | `{value}` | `{pass/warn/fail}` |
| Conditional similarity | `{value}` | `{pass/warn/fail}` |
| Aggregate-query similarity | `{value}` | `{pass/warn/fail}` |

**Utility score:** `{utility_score}`

## Integrity

| Metric | Value | Status |
|---|---|---|
| Orphan foreign keys | `{value}` | `{pass/fail}` |
| Cardinality similarity | `{value}` | `{pass/warn/fail}` |

**Integrity score:** `{integrity_score}`

## Governance

- **Environment:** `NON_PROD`
- **Tags:** `SYNTHETIC`, `NON_PRODUCTION`
- **Lineage:** source dataset(s) → synthetic twin(s)
- **Evidence linked via:** `InstitutionalMemory`

## Important limits

This report describes practical engineering checks. It is **not** a differential-privacy proof, a legal anonymization certification, or a guarantee against all re-identification attacks. Review the per-table metrics before sharing the twin.
