# Under-three-minute demo

## 0:00–0:20 — Screen 1: Data asset

Open the UI and show the restricted healthcare asset. Point out:
- `healthcare.patients` and `healthcare.encounters` row counts.
- `PII`, `PHI`, and `RESTRICTED` tags.
- Owner, domain, and the patient → encounters lineage.

Say: “The product team needs realistic test data. Giving them this table exposes patients; random fake rows break the application.”

## 0:20–0:45 — Screen 2: Generation plan

Click **Create safe twin**. Before generating anything, DOPPEL shows how it will interpret DataHub context per field:
- `patient_id` → surrogate identifier.
- `name`, `email` → synthetic replacement.
- `date_of_birth` → distribution-preserving date.
- `diagnosis_code`, `procedure_code` → categorical modelling.
- `claim_amount` → conditional statistical generation.
- `patient_id` foreign key → relationship-preserving remap.

## 0:45–1:25 — Screen 3: Live pipeline

Click **Run pipeline**. The UI streams real SSE stage events from the backend:
- Reading DataHub context.
- Building the generation plan.
- Generating patients and encounters.
- Checking privacy, utility, relationships, and referential integrity.
- Publishing to DataHub.

There are no fake progress timers — the displayed stages match actual backend work.

## 1:25–1:55 — Screen 4: Verification

The final result is the hero:
- `VERIFIED`.
- Exact copied rows: `0`.
- Direct identifier matches: `0`.
- Privacy score, utility score, referential integrity.
- Singling-out risk, correlation similarity, conditional relationship similarity.

Optionally click **View rejected example** to show what a failing privacy gate looks like.

## 1:55–2:25 — Screen 5: DataHub writeback

Show source → synthetic twin lineage and:
- `SYNTHETIC`, `NON_PRODUCTION`, and `DOPPEL_VERIFIED` tags.
- Evidence receipt linked to each asset.
- Expiry timestamp.
- Owner / domain inheritance.

Click **View in DataHub**, **Download twin**, or **Download evidence**.

## 2:25–2:45 — Close

“The developer received useful data. No patient record crossed the boundary. DataHub now knows what was created, why it is safe enough for this use, and when it expires.”
