# Verification thresholds

These are pragmatic engineering thresholds, not statistical proofs. Adjust them for your domain and risk tolerance.

## Privacy gates

| Metric | Pass | Warn | Fail | Required for VERIFIED |
|---|---|---|---|---|
| Exact row overlap | `0` | — | `> 0` | Must be `0` |
| Direct identifier overlap | `0` | — | `> 0` | Must be `0` |
| Quasi-identifier singling-out rate | `< 10%` | `10%–25%` | `> 25%` | Must be `< 25%` |

**Privacy score:** `100.0` required (all privacy metrics must pass).

## Integrity gates

| Metric | Pass | Fail | Required for VERIFIED |
|---|---|---|---|
| Orphan foreign keys | `0` | `> 0` | Must be `0` |
| Cardinality similarity | `>= 85%` | `< 70%` | Must be `>= 70%` |

**Integrity score:** `100.0` required (no orphan keys; cardinality may warn but not fail).

## Utility gates

| Metric | Good | Warn | Fail |
|---|---|---|---|
| Numeric distribution similarity | `>= 85%` | `>= 70%` | `< 70%` |
| Categorical distribution similarity | `>= 90%` | `>= 75%` | `< 75%` |
| Date distribution similarity | `>= 85%` | `>= 70%` | `< 70%` |
| Correlation similarity | `>= 90%` | `>= 75%` | `< 75%` |
| Conditional relationship similarity | `>= 90%` | `>= 75%` | `< 75%` |
| Aggregate-query similarity | `>= 80%` | `>= 65%` | `< 65%` |
| Cardinality similarity | `>= 85%` | `>= 70%` | `< 70%` |
| Null-rate delta | `<= 2%` | `<= 8%` | `> 8%` |

**Utility score:** `>= 70.0` required for `VERIFIED`.

## Decision rule

`VERIFIED` only when:

- `exact_row_overlap == 0`
- `direct_identifier_overlap == 0`
- `privacy_score == 100.0`
- `integrity_score == 100.0`
- `utility_score >= 70.0`
- No metric reports `fail`

Otherwise `REJECTED`.
