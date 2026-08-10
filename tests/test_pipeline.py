from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from app.config import settings
from app.models import GenerateRequest
from app.services.catalog import CatalogService
from app.services.pipeline import DoppelPipeline
from app.services.synthesizer import SyntheticGenerator


@pytest.fixture()
def isolated_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(settings, "doppel_artifact_dir", tmp_path)
    return tmp_path


def test_generator_replaces_identifiers_and_preserves_foreign_keys() -> None:
    context = CatalogService().get_asset("healthcare")
    asset_dir = settings.doppel_data_dir / "healthcare"
    frames = {
        table.name: pd.read_csv(asset_dir / table.file)
        for table in context.tables
    }
    generated = SyntheticGenerator(seed=7).generate_dataset(context, frames, scale=0.25)

    source_ids = set(frames["patients"]["patient_id"].astype(str))
    synthetic_ids = set(generated["patients"].synthetic["patient_id"].astype(str))
    assert source_ids.isdisjoint(synthetic_ids)

    parent_ids = synthetic_ids
    child_ids = set(generated["encounters"].synthetic["patient_id"].astype(str))
    assert child_ids <= parent_ids

    source_emails = set(frames["patients"]["email"].dropna().astype(str))
    synthetic_emails = set(generated["patients"].synthetic["email"].dropna().astype(str))
    assert source_emails.isdisjoint(synthetic_emails)


def test_pipeline_produces_bundle_and_report(isolated_artifacts: Path) -> None:
    report = DoppelPipeline().generate(
        GenerateRequest(asset_id="healthcare", scale=0.2, seed=11, expiry_days=14)
    )

    output = Path(report.output_dir)
    assert report.status == "completed"
    assert report.exact_row_overlap == 0
    assert report.fk_integrity == 100.0
    assert report.privacy_score == 100.0
    assert report.utility_score > 70
    assert (output / "patients_synthetic.csv").exists()
    assert (output / "encounters_synthetic.csv").exists()
    assert (output / "report.json").exists()
    assert (output / f"doppel-{report.run_id}.zip").exists()


def test_fixture_publish_writes_mutation_preview(
    isolated_artifacts: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "doppel_mode", "fixture")
    pipeline = DoppelPipeline()
    report = pipeline.generate(GenerateRequest(scale=0.1, seed=17))
    published = pipeline.publish(report.run_id)

    assert published.publish_result is not None
    assert published.publish_result["mode"] == "fixture"
    assert Path(report.output_dir, "datahub-mutation-preview.json").exists()


def test_full_dataset_is_verified(isolated_artifacts: Path) -> None:
    report = DoppelPipeline().generate(
        GenerateRequest(asset_id="healthcare", scale=1.0, seed=42, expiry_days=30)
    )
    assert report.decision == "VERIFIED"
    assert report.exact_row_overlap == 0
    assert report.fk_integrity == 100.0
    assert report.privacy_score == 100.0
    assert report.integrity_score == 100.0
    assert report.utility_score > 70


def test_determinism(isolated_artifacts: Path) -> None:
    request = GenerateRequest(asset_id="healthcare", scale=0.5, seed=123, expiry_days=7)
    report1 = DoppelPipeline().generate(request)
    report2 = DoppelPipeline().generate(request)

    for table in ("patients", "encounters"):
        df1 = pd.read_csv(Path(report1.output_dir) / f"{table}_synthetic.csv")
        df2 = pd.read_csv(Path(report2.output_dir) / f"{table}_synthetic.csv")
        assert df1.equals(df2), f"{table} differs between identical-seed runs"


def test_different_seeds_produce_different_data(isolated_artifacts: Path) -> None:
    report1 = DoppelPipeline().generate(
        GenerateRequest(asset_id="healthcare", scale=0.5, seed=1, expiry_days=7)
    )
    report2 = DoppelPipeline().generate(
        GenerateRequest(asset_id="healthcare", scale=0.5, seed=2, expiry_days=7)
    )

    ids1 = set(pd.read_csv(Path(report1.output_dir) / "patients_synthetic.csv")["patient_id"])
    ids2 = set(pd.read_csv(Path(report2.output_dir) / "patients_synthetic.csv")["patient_id"])
    assert ids1.isdisjoint(ids2)


def test_no_source_identifiers_survive(isolated_artifacts: Path) -> None:
    source = pd.read_csv(settings.doppel_data_dir / "healthcare" / "patients.csv")
    report = DoppelPipeline().generate(
        GenerateRequest(asset_id="healthcare", scale=1.0, seed=55, expiry_days=7)
    )
    synthetic = pd.read_csv(Path(report.output_dir) / "patients_synthetic.csv")

    identifier_columns = ["patient_id", "first_name", "last_name", "email", "postal_code"]
    for column in identifier_columns:
        source_values = set(source[column].dropna().astype(str))
        synthetic_values = set(synthetic[column].dropna().astype(str))
        assert source_values.isdisjoint(
            synthetic_values
        ), f"{column} value leaked from source"


def test_synthetic_encounters_reference_synthetic_patients(isolated_artifacts: Path) -> None:
    report = DoppelPipeline().generate(
        GenerateRequest(asset_id="healthcare", scale=1.0, seed=77, expiry_days=7)
    )
    patients = pd.read_csv(Path(report.output_dir) / "patients_synthetic.csv")
    encounters = pd.read_csv(Path(report.output_dir) / "encounters_synthetic.csv")

    parent_ids = set(patients["patient_id"].astype(str))
    child_ids = set(encounters["patient_id"].astype(str))
    orphan_count = len(child_ids - parent_ids)
    assert orphan_count == 0


def test_catalog_discovers_multiple_assets() -> None:
    assets = CatalogService().list_assets()
    asset_ids = {asset.id for asset in assets}
    assert {"healthcare", "finance", "retail"}.issubset(asset_ids)


@pytest.mark.parametrize("asset_id", ["finance", "retail"])
def test_new_assets_verify(isolated_artifacts: Path, asset_id: str) -> None:
    report = DoppelPipeline().generate(
        GenerateRequest(asset_id=asset_id, scale=1.0, seed=42, expiry_days=7)
    )
    assert report.decision == "VERIFIED"
    assert report.exact_row_overlap == 0
    assert report.fk_integrity == 100.0
    assert report.privacy_score == 100.0
    assert report.integrity_score == 100.0
    assert report.utility_score > 70
