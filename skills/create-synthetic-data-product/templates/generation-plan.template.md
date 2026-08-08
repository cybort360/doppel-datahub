# Generation Plan: `{source_asset_name}` → Synthetic Twin

## Source asset

- **URN(s):** `{source_urn}`
- **Owner:** `{owner}`
- **Domain:** `{domain}`
- **Target environment:** `{target_env}`
- **Scale factor:** `{scale}`
- **Seed:** `{seed}`
- **Expiry:** `{expiry_days} days`

## Table mapping

| Source table | Synthetic table | Primary key | Foreign keys |
|---|---|---|---|
| `{table_name}` | `{table_name}_synthetic` | `{pk}` | `{fks}` |

## Column strategies

| Table | Column | Semantic type | Tags / terms | Strategy | Reason |
|---|---|---|---|---|---|
| `{table}` | `{column}` | `{semantic}` | `{tags}` | `{strategy}` | `{reason}` |

## Sensitive columns

| Column | Risk category | Mitigation |
|---|---|---|
| `{column}` | Direct identifier | `{mitigation}` |
| `{column}` | Quasi-identifier | `{mitigation}` |
| `{column}` | Sensitive attribute | `{mitigation}` |

## Relationship preservation

| Parent table | Child table | Foreign key | Cardinality target |
|---|---|---|---|
| `{parent}` | `{child}` | `{fk_column}` | Preserve source shape after mean-normalization |

## Verification thresholds

| Gate | Threshold |
|---|---|
| Exact row overlap | `0` |
| Direct identifier overlap | `0` |
| Privacy score | `100.0` |
| Integrity score | `100.0` |
| Utility score | `>= 70.0` |
| Singling-out rate | `< 10%` pass, `10%-25%` warn, `> 25%` fail |
