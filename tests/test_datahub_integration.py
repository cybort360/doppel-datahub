from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

try:
    from datahub.metadata.schema_classes import (
        DateTypeClass,
        NumberTypeClass,
        StringTypeClass,
        TimeTypeClass,
    )
except ImportError:
    pytest.importorskip("datahub")

from app.config import settings
from app.models import GenerateRequest, SemanticType
from app.services.catalog import CatalogService
from app.services.datahub import DataHubPublisher
from app.services.pipeline import DoppelPipeline


def _datahub_urn(name: str) -> str:
    return f"urn:li:dataset:(urn:li:dataPlatform:postgres,clinical.{name},PROD)"


class _FakeField:
    def __init__(
        self,
        name: str,
        native_type: str,
        field_type: Any,
        nullable: bool = True,
        tags: list[str] | None = None,
        description: str = "",
    ) -> None:
        self.fieldPath = name
        self.nativeDataType = native_type
        self.type = MagicMock()
        self.type.type = field_type
        self.nullable = nullable
        self.globalTags = None
        if tags:
            self.globalTags = MagicMock()
            self.globalTags.tags = [MagicMock(tag=f"urn:li:tag:{tag}") for tag in tags]
        self.description = description
        self.glossaryTerms = None


class _FakeSchema:
    def __init__(self, fields: list[_FakeField], primary_key: str) -> None:
        self.fields = fields
        self.primaryKeys = [primary_key]
        self.foreignKeys = []


@pytest.fixture()
def datahub_catalog(monkeypatch: pytest.MonkeyPatch) -> CatalogService:
    monkeypatch.setattr(settings, "doppel_mode", "datahub")

    def _aspect(urn: str, aspect_cls: Any) -> Any:
        from datahub.metadata.schema_classes import (
            DatasetPropertiesClass,
            DomainsClass,
            GlobalTagsClass,
            OwnershipClass,
            SchemaMetadataClass,
        )

        name = urn.split(",")[1].rsplit(".", 1)[-1]
        if aspect_cls is DatasetPropertiesClass:
            return DatasetPropertiesClass(
                name=name,
                description=f"{name} table",
                customProperties={"doppel_source_file": f"{name}.csv"},
            )
        if aspect_cls is GlobalTagsClass:
            return GlobalTagsClass(tags=[])
        if aspect_cls is OwnershipClass:
            return OwnershipClass(owners=[])
        if aspect_cls is DomainsClass:
            return DomainsClass(domains=["urn:li:domain:clinical-operations"])
        if aspect_cls is SchemaMetadataClass:
            if name == "patients":
                fields = [
                    _FakeField(
                        "patient_id", "object", StringTypeClass(), False, ["PRIMARY_KEY", "PII"]
                    ),
                    _FakeField("first_name", "object", StringTypeClass(), False, ["PII"]),
                    _FakeField("last_name", "object", StringTypeClass(), False, ["PII"]),
                    _FakeField("email", "object", StringTypeClass(), True, ["PII"]),
                    _FakeField(
                        "date_of_birth",
                        "object",
                        DateTypeClass(),
                        False,
                        ["PHI", "QUASI_IDENTIFIER"],
                    ),
                    _FakeField(
                        "postal_code",
                        "object",
                        StringTypeClass(),
                        False,
                        ["PII", "QUASI_IDENTIFIER"],
                    ),
                    _FakeField("sex", "object", StringTypeClass(), False, ["QUASI_IDENTIFIER"]),
                    _FakeField("diagnosis_code", "object", StringTypeClass(), False, ["PHI"]),
                    _FakeField("risk_score", "float64", NumberTypeClass(), False, ["PHI"]),
                    _FakeField("visits_last_year", "int64", NumberTypeClass(), False, []),
                ]
                return _FakeSchema(fields, "patient_id")
            if name == "encounters":
                fields = [
                    _FakeField("encounter_id", "object", StringTypeClass(), False, ["PRIMARY_KEY"]),
                    _FakeField(
                        "patient_id", "object", StringTypeClass(), False, ["FOREIGN_KEY", "PII"]
                    ),
                    _FakeField("encounter_date", "object", TimeTypeClass(), False, ["PHI"]),
                    _FakeField("facility", "object", StringTypeClass(), False, []),
                    _FakeField("procedure_code", "object", StringTypeClass(), False, ["PHI"]),
                    _FakeField("claim_amount", "float64", NumberTypeClass(), True, ["FINANCIAL"]),
                    _FakeField("status", "object", StringTypeClass(), False, []),
                ]
                schema = _FakeSchema(fields, "encounter_id")
                schema.foreignKeys = [
                    MagicMock(
                        fieldPath="patient_id",
                        foreignDataset=_datahub_urn("patients"),
                        foreignFields=["patient_id"],
                    )
                ]
                return schema
        return None

    fake_graph = MagicMock()
    fake_graph.get_aspect.side_effect = _aspect

    monkeypatch.setattr(
        "datahub.ingestion.graph.client.DataHubGraph",
        lambda *args, **kwargs: fake_graph,
    )
    monkeypatch.setattr(
        "app.services.catalog.DataHubGraph",
        lambda *args, **kwargs: fake_graph,
    )
    return CatalogService()


def test_datahub_catalog_builds_context(datahub_catalog: CatalogService) -> None:
    context = datahub_catalog.get_asset("healthcare")
    assert context.id == "healthcare"
    assert len(context.tables) == 2

    patients = next(table for table in context.tables if table.name == "patients")
    encounters = next(table for table in context.tables if table.name == "encounters")

    assert patients.primary_key == "patient_id"
    assert patients.file == "patients.csv"
    assert any(
        column.name == "email" and column.semantic_type == SemanticType.EMAIL
        for column in patients.columns
    )
    assert any(
        column.name == "risk_score" and column.semantic_type == SemanticType.NUMERIC
        for column in patients.columns
    )

    assert encounters.primary_key == "encounter_id"
    assert len(encounters.foreign_keys) == 1
    assert encounters.foreign_keys[0].references_table == "patients"


def test_datahub_pipeline_uses_context(
    datahub_catalog: CatalogService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "doppel_artifact_dir", tmp_path)

    pipeline = DoppelPipeline()
    report = pipeline.generate(
        GenerateRequest(asset_id="healthcare", scale=0.1, seed=19, expiry_days=7)
    )

    assert report.status == "completed"
    assert report.fk_integrity == 100.0
    assert report.expires_at is not None
    assert len(report.source_table_urns) == 2


def test_mutation_preview_contains_scores_and_timestamps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "doppel_artifact_dir", tmp_path)

    publisher = DataHubPublisher()
    pipeline = DoppelPipeline()
    report = pipeline.generate(
        GenerateRequest(asset_id="healthcare", scale=0.1, seed=23, expiry_days=14)
    )
    context = CatalogService().get_asset("healthcare")
    preview = publisher._mutation_preview(context, report)

    assert len(preview["synthetic_assets"]) == 2
    asset = preview["synthetic_assets"][0]
    assert "SYNTHETIC" in asset["tags"]
    assert "NON_PRODUCTION" in asset["tags"]
    assert "privacy_score" in asset["customProperties"]
    assert "utility_score" in asset["customProperties"]
    assert "integrity_score" in asset["customProperties"]
    assert "generated_at" in asset["customProperties"]
    assert "expires_at" in asset["customProperties"]
    assert "source_dataset" in asset["customProperties"]
    assert asset["lineage"]["upstream"]


class _FakeEmitter:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.mcps: list[Any] = []

    def emit_mcp(self, mcp: Any) -> None:
        self.mcps.append(mcp)

    def close(self) -> None:
        pass

    def test_connection(self) -> None:
        pass


def test_live_publish_emits_synthetic_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "doppel_artifact_dir", tmp_path)
    monkeypatch.setattr(settings, "doppel_mode", "fixture")

    pipeline = DoppelPipeline()
    report = pipeline.generate(
        GenerateRequest(asset_id="healthcare", scale=0.1, seed=41, expiry_days=7)
    )
    context = CatalogService().get_asset("healthcare")

    monkeypatch.setattr(settings, "doppel_mode", "datahub")
    monkeypatch.setattr("datahub.emitter.rest_emitter.DatahubRestEmitter", _FakeEmitter)

    publisher = DataHubPublisher()
    result = publisher.publish(context, report)

    assert result["mode"] == "datahub"
    assert result["status"] == "published"

    emitted_urns = result["emitted"]
    synthetic_urns = [urn for urn in emitted_urns if urn.startswith("urn:li:dataset:")]
    assert len(synthetic_urns) == 2
    assert all("postgres" in urn for urn in synthetic_urns)

    # Aspects are overwritten on every run, so re-publishing is idempotent.
    result2 = publisher.publish(context, report)
    assert set(result2["emitted"]) == set(result["emitted"])


@pytest.mark.skipif(
    not settings.live_datahub,
    reason="Live DataHub integration test only runs when DOPPEL_MODE=datahub",
)
def test_live_datahub_roundtrip() -> None:
    pipeline = DoppelPipeline()
    report = pipeline.generate(
        GenerateRequest(
            asset_id="healthcare",
            scale=0.1,
            seed=29,
            expiry_days=7,
            publish_after_generation=True,
        )
    )
    assert report.publish_result is not None
    assert report.publish_result.get("mode") == "datahub"
    assert len(report.publish_result.get("emitted", [])) == 2
