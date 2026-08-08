from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from faker import Faker

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "healthcare"
OUT.mkdir(parents=True, exist_ok=True)

rng = np.random.default_rng(20260806)
fake = Faker("en_US")
fake.seed_instance(20260806)

n_patients = 1200
patient_ids = [f"PAT-{i:06d}" for i in range(1, n_patients + 1)]
sexes = rng.choice(["F", "M", "X"], n_patients, p=[0.49, 0.49, 0.02])
diagnoses = rng.choice(
    ["I10", "E11", "J45", "M54", "F41", "Z00"],
    n_patients,
    p=[0.22, 0.18, 0.13, 0.16, 0.12, 0.19],
)
base_risk = {"I10": 0.62, "E11": 0.72, "J45": 0.48, "M54": 0.36, "F41": 0.31, "Z00": 0.12}
risk = np.clip(
    np.array([base_risk[d] for d in diagnoses]) + rng.normal(0, 0.08, n_patients),
    0.01,
    0.99,
)
visits = np.maximum(0, rng.poisson(1 + risk * 5)).astype(int)
ages = np.clip(rng.normal(46 + risk * 20, 17, n_patients), 1, 95).astype(int)
now = pd.Timestamp("2026-08-01")
dobs = [now - pd.Timedelta(days=int(age * 365.25 + rng.integers(0, 365))) for age in ages]

patients = pd.DataFrame(
    {
        "patient_id": patient_ids,
        "first_name": [fake.first_name() for _ in range(n_patients)],
        "last_name": [fake.last_name() for _ in range(n_patients)],
        "email": [fake.unique.email() for _ in range(n_patients)],
        "date_of_birth": [value.strftime("%Y-%m-%d") for value in dobs],
        "postal_code": [fake.postcode() for _ in range(n_patients)],
        "sex": sexes,
        "diagnosis_code": diagnoses,
        "risk_score": np.round(risk, 4),
        "visits_last_year": visits,
    }
)
patients.loc[rng.choice(n_patients, 24, replace=False), "email"] = None
patients.to_csv(OUT / "patients.csv", index=False)

n_encounters = 4200
patient_weights = 0.2 + risk + visits / max(visits.max(), 1)
patient_weights = patient_weights / patient_weights.sum()
enc_patient_ids = rng.choice(patient_ids, n_encounters, p=patient_weights)
procedures = rng.choice(
    ["CONSULT", "LAB", "XRAY", "THERAPY", "SURGERY", "FOLLOW_UP"],
    n_encounters,
    p=[0.26, 0.21, 0.13, 0.15, 0.06, 0.19],
)
amount_base = {
    "CONSULT": 85,
    "LAB": 140,
    "XRAY": 230,
    "THERAPY": 110,
    "SURGERY": 1800,
    "FOLLOW_UP": 60,
}
claim_amounts = np.array([max(15, rng.lognormal(np.log(amount_base[p]), 0.35)) for p in procedures])
facilities = rng.choice(
    ["North Clinic", "Central Hospital", "Riverside Care", "West Diagnostic"],
    n_encounters,
    p=[0.26, 0.34, 0.22, 0.18],
)
statuses = rng.choice(["PAID", "PENDING", "DENIED"], n_encounters, p=[0.73, 0.19, 0.08])
dates = [now - pd.Timedelta(days=int(rng.integers(0, 730))) for _ in range(n_encounters)]

encounters = pd.DataFrame(
    {
        "encounter_id": [f"ENC-{i:07d}" for i in range(1, n_encounters + 1)],
        "patient_id": enc_patient_ids,
        "encounter_date": [value.strftime("%Y-%m-%d") for value in dates],
        "facility": facilities,
        "procedure_code": procedures,
        "claim_amount": np.round(claim_amounts, 2),
        "status": statuses,
    }
)
encounters.loc[rng.choice(n_encounters, 50, replace=False), "claim_amount"] = np.nan
encounters.to_csv(OUT / "encounters.csv", index=False)

context = {
    "id": "healthcare",
    "name": "Clinical Operations Twin",
    "description": "Synthetic patient and encounter data for privacy-safe development and testing.",
    "domain": "Clinical Operations",
    "owner": "Data Platform Team",
    "source_urn": "urn:li:dataset:(urn:li:dataPlatform:postgres,clinical.patient_operations,PROD)",
    "governance_summary": [
        "Direct identifiers are tagged and must never be copied.",
        "Patient-to-encounter relationships must remain valid.",
        "Generated assets expire after a declared non-production window.",
        "Aggregate distributions should remain useful for product testing.",
    ],
    "tables": [
        {
            "name": "patients",
            "file": "patients.csv",
            "urn": "urn:li:dataset:(urn:li:dataPlatform:postgres,clinical.patients,PROD)",
            "description": (
                "Patient registry containing direct identifiers and clinical segmentation."
            ),
            "domain": "Clinical Operations",
            "owner": "Patient Data Team",
            "tags": ["PII", "PHI", "RESTRICTED"],
            "primary_key": "patient_id",
            "foreign_keys": [],
            "columns": [
                {
                    "name": "patient_id",
                    "dtype": "object",
                    "semantic_type": "identifier",
                    "nullable": False,
                    "tags": ["PRIMARY_KEY", "PII"],
                    "description": "Internal patient identifier.",
                    "strategy": "surrogate_id",
                },
                {
                    "name": "first_name",
                    "dtype": "object",
                    "semantic_type": "person_name",
                    "nullable": False,
                    "tags": ["PII"],
                    "description": "Patient given name.",
                    "strategy": "faker_name",
                },
                {
                    "name": "last_name",
                    "dtype": "object",
                    "semantic_type": "person_name",
                    "nullable": False,
                    "tags": ["PII"],
                    "description": "Patient family name.",
                    "strategy": "faker_name",
                },
                {
                    "name": "email",
                    "dtype": "object",
                    "semantic_type": "email",
                    "nullable": True,
                    "tags": ["PII"],
                    "description": "Patient email address.",
                    "strategy": "reserved_domain_email",
                },
                {
                    "name": "date_of_birth",
                    "dtype": "object",
                    "semantic_type": "date_of_birth",
                    "nullable": False,
                    "tags": ["PHI", "QUASI_IDENTIFIER"],
                    "description": "Patient birth date.",
                    "strategy": "distribution_preserving_date",
                },
                {
                    "name": "postal_code",
                    "dtype": "object",
                    "semantic_type": "postal_code",
                    "nullable": False,
                    "tags": ["PII", "QUASI_IDENTIFIER"],
                    "description": "Patient postal code.",
                    "strategy": "faker_postcode",
                },
                {
                    "name": "sex",
                    "dtype": "object",
                    "semantic_type": "categorical",
                    "nullable": False,
                    "tags": ["QUASI_IDENTIFIER"],
                    "description": "Recorded sex category.",
                    "strategy": "categorical_distribution",
                },
                {
                    "name": "diagnosis_code",
                    "dtype": "object",
                    "semantic_type": "categorical",
                    "nullable": False,
                    "tags": ["PHI"],
                    "description": "Primary diagnosis group.",
                    "strategy": "categorical_distribution",
                },
                {
                    "name": "risk_score",
                    "dtype": "float64",
                    "semantic_type": "numeric",
                    "nullable": False,
                    "tags": ["PHI"],
                    "description": "Normalized clinical risk score.",
                    "strategy": "gaussian_copula",
                },
                {
                    "name": "visits_last_year",
                    "dtype": "int64",
                    "semantic_type": "numeric",
                    "nullable": False,
                    "tags": [],
                    "description": "Count of visits in the prior year.",
                    "strategy": "gaussian_copula",
                },
            ],
        },
        {
            "name": "encounters",
            "file": "encounters.csv",
            "urn": "urn:li:dataset:(urn:li:dataPlatform:postgres,clinical.encounters,PROD)",
            "description": "Clinical encounters and claims linked to patients.",
            "domain": "Clinical Operations",
            "owner": "Claims Analytics Team",
            "tags": ["PHI", "FINANCIAL"],
            "primary_key": "encounter_id",
            "foreign_keys": [
                {
                    "column": "patient_id",
                    "references_table": "patients",
                    "references_column": "patient_id",
                }
            ],
            "columns": [
                {
                    "name": "encounter_id",
                    "dtype": "object",
                    "semantic_type": "identifier",
                    "nullable": False,
                    "tags": ["PRIMARY_KEY"],
                    "description": "Encounter identifier.",
                    "strategy": "surrogate_id",
                },
                {
                    "name": "patient_id",
                    "dtype": "object",
                    "semantic_type": "foreign_key",
                    "nullable": False,
                    "tags": ["FOREIGN_KEY", "PII"],
                    "description": "Patient foreign key.",
                    "strategy": "frequency_preserving_fk",
                },
                {
                    "name": "encounter_date",
                    "dtype": "object",
                    "semantic_type": "datetime",
                    "nullable": False,
                    "tags": ["PHI"],
                    "description": "Encounter date.",
                    "strategy": "distribution_preserving_date",
                },
                {
                    "name": "facility",
                    "dtype": "object",
                    "semantic_type": "categorical",
                    "nullable": False,
                    "tags": [],
                    "description": "Facility where care occurred.",
                    "strategy": "categorical_distribution",
                },
                {
                    "name": "procedure_code",
                    "dtype": "object",
                    "semantic_type": "categorical",
                    "nullable": False,
                    "tags": ["PHI"],
                    "description": "Procedure category.",
                    "strategy": "categorical_distribution",
                },
                {
                    "name": "claim_amount",
                    "dtype": "float64",
                    "semantic_type": "numeric",
                    "nullable": True,
                    "tags": ["FINANCIAL"],
                    "description": "Submitted claim amount.",
                    "strategy": "conditional_on:procedure_code",
                },
                {
                    "name": "status",
                    "dtype": "object",
                    "semantic_type": "categorical",
                    "nullable": False,
                    "tags": [],
                    "description": "Claim adjudication state.",
                    "strategy": "categorical_distribution",
                },
            ],
        },
    ],
}
(OUT / "context.json").write_text(json.dumps(context, indent=2))
print(f"Created fixture at {OUT}")
