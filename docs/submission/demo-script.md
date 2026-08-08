# DOPPEL 3-minute demo script

> Opening line: "This production healthcare dataset contains sensitive patient information. DOPPEL creates a useful development twin without exposing the patients."

## Setup before recording

1. `cp .env.example .env` and ensure `DOPPEL_MODE=fixture` for the no-DataHub version, or set `DOPPEL_MODE=datahub` after bootstrapping.
2. Start the UI: `uvicorn app.main:app --reload`.
3. Open `http://localhost:8000` at 1440px desktop width.
4. (Live path) Run `datahub docker quickstart` and `python scripts/bootstrap_datahub.py` first.

## 0:00–0:15 — The problem: restricted production data

Screen: **Data Asset**

- Show `healthcare.patients` and `healthcare.encounters`.
- Point to row counts (~1,200 patients, ~4,200 encounters).
- Highlight PII fields tagged by DataHub: `patient_id`, `first_name`, `last_name`, `email`, `postal_code`, `date_of_birth`.
- Show the **Production / Restricted** badge and the owner/domain (`Clinical Operations`).
- Say: "Developers need realistic data, but they cannot have these rows."

## 0:15–0:35 — DataHub as the source of truth

Screen: still **Data Asset** / scroll to metadata panel.

- Explain that DOPPEL does not hardcode the mapping.
- Show tags coming from DataHub: `PII`, `PHI`, `RESTRICTED`, `QUASI_IDENTIFIER`, `FINANCIAL`.
- Show schema, primary keys, and the `patient_id` foreign key.
- Show the `patients → encounters` lineage edge.
- Say: "DataHub tells DOPPEL what is sensitive, what relates to what, and who owns it."

## 0:35–1:05 — Generation plan

Screen: **Generation Plan**

- Click **Create Safe Twin**.
- Walk through the column-level plan:
  - `patient_id` → surrogate identifier
  - `first_name`, `last_name` → synthetic name
  - `email` → reserved-domain synthetic email
  - `date_of_birth` → distribution-preserving date
  - `postal_code` → synthetic postcode
  - `diagnosis_code`, `sex`, `facility`, `procedure_code`, `status` → categorical modelling
  - `risk_score`, `visits_last_year` → Gaussian-copula numeric
  - `claim_amount` → conditional on `procedure_code`
  - `encounters.patient_id` → relationship-preserving remap
- Say: "Every decision is driven by the metadata, not by a spreadsheet."

## 1:05–1:35 — Live pipeline

Screen: **Live Pipeline**

- Click **Run pipeline**.
- Watch the real SSE stages update:
  1. Reading DataHub context
  2. Building generation plan
  3. Generating patients
  4. Generating encounters
  5. Checking privacy
  6. Checking utility
  7. Checking relationships
  8. Publishing to DataHub
- No artificial timers; progress reflects actual backend work.

## 1:35–2:05 — Verification result

Screen: **Verification**

- Make the result the hero:
  - **VERIFIED**
  - Exact copied rows: `0`
  - Direct identifier matches: `0`
  - Privacy score: `100.0`
  - Utility score: `~98.7`
  - Referential integrity: `100.0`
  - Singling-out risk: reported and bounded
  - Correlation similarity and conditional relationship similarity visible.
- Hover tooltips to explain what each metric means.
- Say: "Fail-closed: if any gate fails, this page says REJECTED and lists the reasons."

## 2:05–2:30 — DataHub writeback and lineage

Screen: **DataHub Writeback** / switch to DataHub UI at `http://localhost:9002`.

- Show the source → synthetic twin diagram.
- In DataHub, search for `doppel`.
- Open `doppel.healthcare.patients_synthetic`.
- Show:
  - `SYNTHETIC` and `NON_PRODUCTION` tags
  - Owner/domain inherited from source
  - Custom properties: privacy score, utility score, integrity score, generated at, expires at, source dataset
  - Upstream lineage tab: `clinical.patients → doppel.healthcare.patients_synthetic`
- Do the same for `doppel.healthcare.encounters_synthetic` and show the patients → encounters lineage preserved inside the synthetic twin.

## 2:30–2:50 — Evidence and downloads

Screen: back to DOPPEL **DataHub Writeback**.

- Show:
  - Evidence receipt (InstitutionalMemory link to `report.json`)
  - Expiry date
  - Owner/domain
- Click **Download Twin** to show the CSV + ZIP bundle.
- Click **Download Evidence** to show `report.json` with full privacy/utility/integrity metrics.

## 2:50–3:00 — Close

Say:

> "DOPPEL turns governed production data into safe, useful development data — and DataHub carries the context from source to synthetic twin."

## Backup: rejected run

If time permits, change the seed to a value that produces a high singling-out rate or manually trigger a rejected fixture. Show that the UI displays **REJECTED**, lists the failing gates, and refuses to publish.
