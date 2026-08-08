# DataHub aspects used

## Aspects to read from the source asset

| Aspect | What to extract |
|---|---|
| `DatasetProperties` | Name, description, custom properties (including `doppel_source_file` if present). |
| `SchemaMetadata` | Fields, native types, nullability, `primaryKeys`, `foreignKeys`. |
| `GlobalTags` | Sensitivity and governance tags such as `PII`, `PHI`, `RESTRICTED`, `QUASI_IDENTIFIER`, `FINANCIAL`, `PRIMARY_KEY`, `FOREIGN_KEY`. |
| `GlossaryTerms` | Semantic hints that influence generation strategy. |
| `Ownership` | Owner to carry forward to the synthetic asset. |
| `Domains` | Domain to carry forward to the synthetic asset. |
| `UpstreamLineage` | Existing upstreams to preserve in the synthetic twin's lineage story. |

## Aspects to write to the synthetic asset

| Aspect | What to emit |
|---|---|
| `DatasetProperties` | Synthetic name, description, and custom properties: `privacy_score`, `utility_score`, `integrity_score`, `fk_integrity`, `exact_row_overlap`, `generated_at`, `expires_at`, `expires_in_days`, `source_dataset`, `source_asset`, `doppel_run_id`, `synthetic_generation_strategy`. |
| `SchemaMetadata` | Same schema as the source, with synthetic primary/foreign keys preserved. |
| `GlobalTags` | `SYNTHETIC`, `NON_PRODUCTION`. |
| `Ownership` | Owner inherited from the source. |
| `Domains` | Domain inherited from the source. |
| `UpstreamLineage` | Upstream edge from the synthetic dataset to its source dataset with type `TRANSFORMED`. |
| `InstitutionalMemory` | Link to the evidence report with a description of scores and run id. |
