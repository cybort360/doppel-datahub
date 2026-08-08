# Threat model

## Assets

- Source records containing direct identifiers and protected health information.
- DataHub metadata describing sensitivity, ownership, schema, and relationships.
- Synthetic outputs that may still reveal aggregate or quasi-identifier patterns.
- DataHub credentials used for metadata read and write operations.

## Trust boundaries

1. Source data enters the deterministic generation process.
2. Governance context enters from DataHub or the checked-in fixture.
3. Generated data crosses into a non-production artifact directory.
4. Verification results cross into DataHub as metadata.

## Primary threats and controls

| Threat | Control |
|---|---|
| Direct identifiers copied into output | Dedicated generators plus source/synthetic intersection checks |
| Full source rows reproduced | SHA-256 normalized row-overlap check |
| Child records point to missing synthetic parents | Parent-first generation and fail-closed foreign-key validation |
| Synthetic data is mistaken for anonymous or production-safe data | Explicit warnings, `SYNTHETIC` and `NON_PRODUCTION` tags, expiry metadata |
| Utility claims are cosmetic | KS, total-variation, date, correlation, conditional aggregate, null-rate, schema, relationship, and aggregate-query checks |
| Fail-closed approval | A twin is `REJECTED` unless every privacy/integrity gate passes and utility clears the documented threshold |
| Metadata writer receives excessive authority | Separate token configuration; only dataset properties, tags, and lineage are emitted |
| Partial metadata causes unsafe defaults | Checked-in semantic contract remains the fallback; live aspects only enrich it |
| Seed enables reconstruction of source data | The seed reproduces generated randomness, not source sampling order or source identifiers |

## Known limits

DOPPEL does not currently provide differential privacy, formal re-identification guarantees, cryptographic isolation, row-level access control, or legal compliance certification. A real deployment should add stronger privacy models, destination authorization, retention enforcement, audit logging, and independent privacy review.
