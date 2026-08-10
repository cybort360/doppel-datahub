from __future__ import annotations

import pandas as pd
import pytest

from app.config import settings
from app.models import GenerateRequest, Metric, TableReport
from app.services.catalog import CatalogService
from app.services.evaluation import (
    evaluate_cardinality,
    foreign_key_integrity,
    render_decision,
    score_reports,
    summarize_integrity,
    summarize_privacy,
    summarize_utility,
)
from app.services.pipeline import DoppelPipeline
from app.services.synthesizer import SyntheticGenerator


@pytest.fixture()
def full_run(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch):
    tmp = tmp_path_factory.mktemp("doppel-full")
    monkeypatch.setattr(settings, "doppel_artifact_dir", tmp)
    return DoppelPipeline().generate(
        GenerateRequest(asset_id="healthcare", scale=1.0, seed=42, expiry_days=30)
    )


def test_score_reports_returns_zero_leakage_for_verified_run(full_run):
    privacy_score, utility_score, exact_overlap, direct_overlap = score_reports(full_run.tables)
    assert privacy_score == 100.0
    assert exact_overlap == 0
    assert direct_overlap == 0
    assert utility_score > 70


def test_render_decision_verifies_clean_run(full_run):
    privacy_summary = summarize_privacy(full_run.tables)
    utility_summary = summarize_utility(full_run.tables)
    integrity_summary = summarize_integrity(full_run.integrity_score, [])

    decision, reasons = render_decision(
        privacy_score=full_run.privacy_score,
        utility_score=full_run.utility_score,
        integrity_score=full_run.integrity_score,
        exact_overlap=full_run.exact_row_overlap,
        direct_identifier_overlap=privacy_summary["direct_identifier_overlap"],
        privacy_summary=privacy_summary,
        utility_summary=utility_summary,
        integrity_summary=integrity_summary,
    )
    assert decision == "VERIFIED"
    assert any("cleared threshold" in reason for reason in reasons)


def test_render_decision_rejects_exact_row_leakage():
    dummy_report = TableReport(
        table="patients",
        source_rows=10,
        synthetic_rows=10,
        privacy_metrics=[
            Metric(name="exact_row_overlap", value=1, status="fail", detail=""),
            Metric(name="direct_identifier_overlap", value=0, status="pass", detail=""),
        ],
        utility_metrics=[
            Metric(name="schema_match", value=1.0, status="pass", detail=""),
        ],
    )
    privacy_summary = summarize_privacy([dummy_report])
    utility_summary = summarize_utility([dummy_report])
    integrity_summary = summarize_integrity(100.0, [])

    decision, reasons = render_decision(
        privacy_score=50.0,
        utility_score=100.0,
        integrity_score=100.0,
        exact_overlap=1,
        direct_identifier_overlap=0,
        privacy_summary=privacy_summary,
        utility_summary=utility_summary,
        integrity_summary=integrity_summary,
    )
    assert decision == "REJECTED"
    assert any("complete source row" in reason for reason in reasons)


def test_render_decision_rejects_low_utility():
    dummy_report = TableReport(
        table="patients",
        source_rows=10,
        synthetic_rows=10,
        privacy_metrics=[
            Metric(name="exact_row_overlap", value=0, status="pass", detail=""),
            Metric(name="direct_identifier_overlap", value=0, status="pass", detail=""),
        ],
        utility_metrics=[
            Metric(name="schema_match", value=1.0, status="pass", detail=""),
            Metric(name="distribution:bad", value=0.1, status="fail", detail=""),
        ],
    )
    privacy_summary = summarize_privacy([dummy_report])
    utility_summary = summarize_utility([dummy_report])
    integrity_summary = summarize_integrity(100.0, [])

    decision, reasons = render_decision(
        privacy_score=100.0,
        utility_score=55.0,
        integrity_score=100.0,
        exact_overlap=0,
        direct_identifier_overlap=0,
        privacy_summary=privacy_summary,
        utility_summary=utility_summary,
        integrity_summary=integrity_summary,
    )
    assert decision == "REJECTED"
    assert any("Utility score" in reason for reason in reasons)


def test_foreign_key_integrity_detects_orphans():
    generated = {
        "patients": pd.DataFrame({"patient_id": ["p1", "p2"]}),
        "encounters": pd.DataFrame({"patient_id": ["p1", "p3"]}),
    }
    context = CatalogService().get_asset("healthcare")
    score, metrics = foreign_key_integrity(generated, context.tables)
    assert score == 0.0
    orphan_metric = next(m for m in metrics if m.name == "fk:encounters.patient_id")
    assert orphan_metric.value == 1


def test_cardinality_preserved_at_full_scale():
    context = CatalogService().get_asset("healthcare")
    asset_dir = settings.doppel_data_dir / "healthcare"
    frames = {
        table.name: pd.read_csv(asset_dir / table.file)
        for table in context.tables
    }
    generated = SyntheticGenerator(seed=99).generate_dataset(context, frames, scale=1.0)

    fk = context.tables[1].foreign_keys[0]
    metric = evaluate_cardinality(
        frames["patients"],
        frames["encounters"],
        generated["patients"].synthetic,
        generated["encounters"].synthetic,
        fk,
    )
    assert metric.value >= 0.99


def test_relationship_and_aggregate_metrics_present(full_run):
    names = [m.name for table in full_run.tables for m in table.utility_metrics]
    assert any("relationship:diagnosis_to_procedure" in n for n in names)
    assert any("aggregate_query:" in n for n in names)


def test_singling_out_metric_computed_and_bounded(full_run):
    singling_metrics = [
        m
        for table in full_run.tables
        for m in table.privacy_metrics
        if m.name == "quasi_identifier_singling_out_rate"
    ]
    assert singling_metrics
    for metric in singling_metrics:
        assert 0.0 <= float(metric.value) <= 1.0
