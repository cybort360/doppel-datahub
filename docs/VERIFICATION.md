# DOPPEL verification and scoring

DOPPEL does not claim to anonymize data. It generates a **non-production synthetic twin**
and runs a transparent, fail-closed battery of lightweight checks. A twin is only marked
`VERIFIED` when every required gate passes.

## Decision gate

```json
{
  "decision": "VERIFIED | REJECTED",
  "reasons": ["..."],
  "privacy_score": 100.0,
  "utility_score": 98.7,
  "integrity_score": 100.0
}
```

A run receives `VERIFIED` only if **all** of the following are true:

| Gate | Threshold | Why |
|---|---|---|
| Privacy score | `100.0` | Every privacy metric must be `pass` |
| Integrity score | `100.0` | No orphan foreign keys and cardinality shape preserved |
| Utility score | `>= 70.0` | Aggregate usefulness is acceptable |
| Exact row overlap | `0` | No complete source row was reproduced |
| Direct identifier overlap | `0` | No source identifier value survived |
| No failed metric | `0` | Any `fail` status in privacy/integrity/utility rejects the run |

If any gate fails, `decision` is `REJECTED` and `reasons` lists every failure.

## Privacy checks

### Exact row overlap
Every synthetic row is SHA-256 hashed after normalizing nulls and column order. The
metric counts how many hashes appear in both source and synthetic. Expected value: `0`.

### Direct identifier overlap
For every column classified as an identifier, email, person name, or postal code, DOPPEL
computes the set intersection of source and synthetic values. The metric is the total
intersection count across those columns. Expected value: `0`.

### Quasi-identifier singling-out rate
Columns tagged `QUASI_IDENTIFIER` are generalized:

- Dates → decade (e.g., `1990`)
- Postal codes → first three characters
- Everything else → string value

The metric is the fraction of synthetic rows that end up in a generalized group with
fewer than five members. It is intentionally strict: even if no direct identifier leaks,
a rare combination of quasi-identifiers can single a record out.

- `pass`: `< 10%` of rows in small groups
- `warn`: `10%–25%`
- `fail`: `> 25%`

## Integrity checks

### Foreign-key integrity
For every declared foreign key, DOPPEL counts how many child values have no matching
parent in the synthetic output. Expected value: `0`.

### Cardinality preservation
For each parent/child relationship, DOPPEL compares the **shape** of the
children-per-parent distribution. Counts are mean-normalized so the metric is not
confused by the overall scale factor. A score of `1.0` means the one-to-many shape is
identical; `0.0` means completely different.

## Utility checks

### Per-column distributions
- **Numeric** columns: `1 - KS_statistic` from a two-sample Kolmogorov–Smirnov test.
- **Categorical/boolean** columns: `1 - total_variation_distance` between value PMFs.
- **Date/datetime** columns: KS over parsed timestamps.

### Null-rate similarity
Mean absolute delta between source and synthetic null rates per column.

### Correlation similarity
Mean absolute difference of pairwise Pearson correlations for numeric columns,
converted to a `0–1` similarity score.

### Conditional relationships
For columns marked `conditional_on:<group>`, DOPPEL compares mean values per group
(e.g., `claim_amount` per `procedure_code`).

### Healthcare-specific relationships
- **diagnosis → procedure**: TVD similarity of the joint distribution of patient
  `diagnosis_code` and encounter `procedure_code`.
- **age group → diagnosis**: TVD similarity of the joint distribution of patient age
  decade and `diagnosis_code`.

### Aggregate-query similarity
A small set of representative aggregate queries are run on source and synthetic:

- Encounter volume by facility
- Mean claim amount by procedure code
- Patient volume by age group

Each is scored with a `0–1` similarity metric.

## What the scores do **NOT** guarantee

- **Not differential privacy.** An attacker with outside knowledge may still make
  inferences about specific individuals.
- **Not a legal anonymization certification.** DOPPEL is a development/testing aid,
  not a substitute for privacy review or compliance.
- **Not a bound on membership inference.** The checks detect obvious leakage, not
  sophisticated model-based attacks.
- **Not a guarantee of downstream fairness.** Correlations and aggregates are
  preserved on average; small subgroups may still be distorted.
- **Not production-safe by default.** Outputs are tagged `SYNTHETIC` and
  `NON_PRODUCTION` and carry an expiry. Treat them accordingly.

## Interpreting a report

A `VERIFIED` report means the twin cleared the documented engineering gates. It does
not mean the data is safe for every use. Always review the per-table metrics in
`report.json`, especially any `warn` statuses, before sharing a twin.
