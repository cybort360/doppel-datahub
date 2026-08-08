# Judging criteria map

This file maps each hackathon judging criterion to concrete evidence in the repository.

## 1. Use of DataHub

| Claim | Proof |
|---|---|
| Reads schema, keys, tags, terms, ownership, domains, lineage | `app/services/catalog.py` `_load_from_datahub()` and `app/services/datahub.py` `enrich_context()` |
| Uses governance tags to drive generation strategy | `app/services/catalog.py` `_infer_semantic_type()` and `_strategy_for_semantic()` |
| Publishes synthetic datasets with tags, lineage, scores, expiry | `app/services/datahub.py` `_publish_live()` |
| Evidence linked as `InstitutionalMemory` | `app/services/datahub.py` lines 250–262 |
| Live path exercised | `examples/verified-run/` produced from `DOPPEL_MODE=datahub` run `6f80e4ff1c97` |
| DataHub Skill contribution | `skills/create-synthetic-data-product/` |

## 2. Technical Execution

| Claim | Proof |
|---|---|
| Deterministic generation | `tests/test_pipeline.py` `test_determinism` and `test_different_seeds_produce_different_data` |
| Foreign-key integrity | `tests/test_pipeline.py` `test_synthetic_encounters_reference_synthetic_patients` and `test_cardinality_preserved_at_full_scale` |
| Direct identifier separation | `tests/test_pipeline.py` `test_no_source_identifiers_survive` |
| Exact-row overlap detection | `tests/test_evaluation.py` `test_render_decision_rejects_exact_row_leakage` |
| Fail-closed decision | `app/services/evaluation.py` `render_decision()` and `tests/test_evaluation.py` rejection tests |
| Typechecked source | `pyproject.toml` `[tool.mypy]` and CI `mypy app scripts` |
| Clean-clone setup | `README.md` quickstart and `/tmp/doppel-clean-test` verification |

## 3. Originality

| Claim | Proof |
|---|---|
| Metadata-governed synthetic twin workflow | README sections *Why DataHub is essential* and *How it works* |
| Per-column strategy derived from catalog semantics | `app/services/catalog.py` generation plan |
| Verification as a publish gate, not a report afterthought | `app/services/pipeline.py` `render_decision()` before publish |
| Reusable agent skill | `skills/create-synthetic-data-product/SKILL.md` |

## 4. Real-World Usefulness

| Claim | Proof |
|---|---|
| Solves a common data-platform problem | `docs/submission/devpost.md` Inspiration and Problem sections |
| Produces CSV bundles ready for development | `app/services/pipeline.py` `_build_bundle()` and `/api/runs/{id}/download` |
| Tags output `NON_PRODUCTION` with expiry | `app/services/datahub.py` tags and custom properties |
| Honest limitations documented | `README.md` *Limitations / threat model* and `docs/THREAT_MODEL.md` |

Known real-world limitations (documented, not hidden):
- Only one demo asset is wired end-to-end (`healthcare`). Generalizing to arbitrary assets requires extending `CatalogService` and source-row connectors.
- Source rows are still read from local CSV files in the demo; a production deployment would stream from the source system.

## 5. Submission Quality

| Claim | Proof |
|---|---|
| README follows required 21-section order | `README.md` |
| Apache 2.0 license | `LICENSE` |
| `.env.example`, locked requirements | repository root |
| GitHub Actions CI | `.github/workflows/ci.yml` |
| Architecture diagram and screenshots | `docs/architecture.svg`, `examples/ui-*.png` |
| Complete example artifacts | `examples/verified-run/` |
| No committed secrets | `.gitignore` and repository inspection |

## 6. Meaningful Open-Source Contribution

| Claim | Proof |
|---|---|
| Reusable DataHub Skill | `skills/create-synthetic-data-product/` with `SKILL.md`, templates, and references |
| Follows upstream conventions | Skill layout matches `datahub-project/datahub-skills/skills/<skill>/` |
| Exact upstream PR commands | `skills/create-synthetic-data-product/README.md` |
| Apache 2.0 licensed | `LICENSE` and skill frontmatter |
