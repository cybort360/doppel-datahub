# DOPPEL technical deep dive

## Threat model and guarantees

DOPPEL is an engineering aid, not a legal anonymization system.

**What it proves:**
- No complete source row is reproduced in the synthetic output.
- No source value from a direct-identifier column appears in the synthetic output.
- All declared foreign-key relationships remain valid.
- Distribution, correlation, and conditional similarities remain within documented thresholds.

**What it does NOT prove:**
- Formal differential privacy.
- Resistance to sophisticated membership-inference or linkage attacks.
- Legal compliance certification.

Every VERIFIED twin is tagged `NON_PRODUCTION` and carries an expiry to reinforce that it is a development artifact.

## Generation strategies

| Semantic type | Strategy | Rationale |
|---|---|---|
| `identifier` | `surrogate_id` | Non-colliding synthetic primary key; never a source value. |
| `foreign_key` | `frequency_preserving_fk` | Remaps to new parent keys while preserving children-per-parent shape. |
| `email` | `reserved_domain_email` | Synthetic address in `example.test`; no real domain. |
| `person_name` | `faker_name` | First/last name plus synthetic suffix; no source name. |
| `date_of_birth` | `distribution_preserving_date` | Empirical date quantiles with bounded jitter, clamped to the latest source date for determinism. |
| `datetime` | `distribution_preserving_date` | Empirical timestamp quantiles with bounded jitter. |
| `postal_code` | `faker_postcode` | Synthetic postcode plus suffix; no source postcode. |
| `numeric` | `gaussian_copula` or `conditional_on:<col>` | Preserves marginals and pairwise correlations; conditioned numerics preserve group means. |
| `categorical` / `boolean` | `categorical_distribution` | Empirical PMF sampling. |

## Determinism

- A fixed `numpy.random.Generator` seed drives all random choices.
- Faker is seeded with the same seed.
- Date clamping uses the maximum source date, not wall-clock time.
- Age-group calculations use a fixed reference date derived from the source data.
- The result: `df1.equals(df2)` for two runs with the same seed and scale.

## Privacy metrics

- **Exact row overlap:** SHA-256 hashes of normalized rows. A `VERIFIED` run must have `0` overlaps.
- **Direct identifier overlap:** Set intersection of values in identifier/name/email/postcode columns. Must be `0`.
- **Singling-out rate:** Quasi-identifier columns are generalized (dates → decade, postcodes → 3-char prefix); the metric is the fraction of synthetic rows in groups smaller than five.

## Utility metrics

- **Distribution similarity:** `1 - KS statistic` for numeric/date columns; `1 - TVD` for categorical columns.
- **Correlation similarity:** mean absolute difference of pairwise Pearson correlations, scaled to [0, 1].
- **Conditional similarity:** mean absolute relative error of group means for numeric columns conditioned on a categorical column.
- **Relationship similarity:** `1 - TVD` of joint distributions (e.g., diagnosis × procedure, age-group × diagnosis).
- **Aggregate-query similarity:** representative queries compared via TVD or relative error.
- **Cardinality similarity:** children-per-parent distribution shape after mean-normalization.

## Fail-closed decision

```python
decision = "VERIFIED" only if:
    privacy_score == 100.0
    integrity_score == 100.0
    utility_score >= 70.0
    exact_row_overlap == 0
    direct_identifier_overlap == 0
    no privacy/integrity/utility metric reports "fail"
```

If any gate fails, the run is `REJECTED` and the report lists explicit reasons.

## DataHub writeback details

For each synthetic table, DOPPEL emits:
- `DatasetProperties` with name, description, and custom properties for scores/timestamps/expiry/source.
- `GlobalTags` with `SYNTHETIC` and `NON_PRODUCTION`.
- `UpstreamLineage` pointing to the source dataset.
- `SchemaMetadata` with fields, primary key, and synthetic-to-synthetic foreign keys.
- `InstitutionalMemory` linking the run's `report.json` as evidence.

All aspects are overwritten on every run, making the pipeline idempotent.

### Evidence limitation

The current implementation links the evidence report as a `file://` URL in `InstitutionalMemory`. This is correct for a local demo, but a production deployment should upload `report.json` to object storage and link that URL instead.

## Reproducing the verified result

```bash
python -m app.cli generate --asset healthcare --scale 1 --seed 42 --expiry-days 30
```

Expected output (fixture mode):

```json
{
  "decision": "VERIFIED",
  "privacy_score": 100.0,
  "utility_score": 98.7,
  "integrity_score": 100.0,
  "exact_row_overlap": 0,
  "fk_integrity": 100.0
}
```

The full evidence report, source/synthetic CSVs, and DataHub mutation preview are written to `artifacts/runs/<run_id>/`.
