# Architecture

```text
DataHub context / fixture
          |
          v
  Catalog + semantic plan
          |
          v
Multi-table synthetic engine
  - surrogate identifiers
  - empirical categorical distributions
  - Gaussian-copula numeric sampling
  - date distributions with jitter
  - frequency-preserving foreign keys
          |
          v
Verification boundary
  - exact-row overlap
  - direct identifier overlap
  - schema fidelity
  - KS / TVD distribution similarity
  - null-rate delta
  - foreign-key integrity
          |
          +--> CSV + report + reproducible ZIP
          |
          +--> DataHub properties + tags + lineage
```

The language-model layer is intentionally absent from authorization and verification. DOPPEL uses metadata to compile a deterministic generation contract and a deterministic acceptance report. An LLM can later help interpret poorly documented columns, but it must not override failed privacy or integrity checks.
