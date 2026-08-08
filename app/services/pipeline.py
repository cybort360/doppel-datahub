from __future__ import annotations

import shutil
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd

from app.config import settings
from app.models import GenerateRequest, RunReport
from app.services.catalog import CatalogService
from app.services.datahub import DataHubPublisher
from app.services.evaluation import (
    evaluate_aggregate_queries,
    evaluate_integrity,
    evaluate_relationships,
    evaluate_table,
    render_decision,
    score_reports,
    summarize_integrity,
    summarize_privacy,
    summarize_utility,
)
from app.services.synthesizer import SyntheticGenerator


class DoppelPipeline:
    def __init__(self) -> None:
        self.catalog = CatalogService()
        self.publisher = DataHubPublisher()

    def generate(
        self,
        request: GenerateRequest,
        event_callback: Callable[[str, str, str], None] | None = None,
    ) -> RunReport:
        def emit(stage: str, status: str, message: str) -> None:
            if event_callback:
                event_callback(stage, status, message)

        emit("context", "running", "Reading DataHub context")
        context = self.catalog.get_asset(request.asset_id)
        context = self.publisher.enrich_context(context)
        emit("context", "complete", f"Loaded {len(context.tables)} tables from {context.domain}")

        emit("plan", "running", "Building generation plan")
        run_id = uuid.uuid4().hex[:12]
        output_dir = settings.doppel_artifact_dir / run_id
        output_dir.mkdir(parents=True, exist_ok=False)

        frames = {
            table.name: pd.read_csv(settings.doppel_data_dir / table.file)
            for table in context.tables
        }
        generator = SyntheticGenerator(seed=request.seed)
        emit("plan", "complete", "Strategies selected per governed field")

        table_reports = []
        synthetic_frames: dict[str, pd.DataFrame] = {}
        synthetic_urns: list[str] = []
        plan_tables: list[dict[str, object]] = []

        generated = generator.generate_dataset(context, frames, request.scale)
        for table in context.tables:
            emit(f"generate_{table.name}", "running", f"Generating {table.name}")
            item = generated[table.name]
            target_name = f"{table.name}_synthetic"
            target_path = output_dir / f"{target_name}.csv"
            item.synthetic.to_csv(target_path, index=False)
            synthetic_frames[table.name] = item.synthetic
            table_reports.append(evaluate_table(table, item.source, item.synthetic))
            source_platform = _platform_from_dataset_urn(table.urn)
            synthetic_urns.append(
                f"urn:li:dataset:(urn:li:dataPlatform:{source_platform},"
                f"doppel.{request.asset_id}.{target_name},{settings.doppel_target_env})"
            )
            plan_tables.append(
                {
                    "table": table.name,
                    "source_rows": len(item.source),
                    "synthetic_rows": len(item.synthetic),
                    "primary_key": table.primary_key,
                    "foreign_keys": [fk.model_dump() for fk in table.foreign_keys],
                    "strategies": {
                        column.name: column.strategy or column.semantic_type.value
                        for column in table.columns
                    },
                }
            )
            emit(f"generate_{table.name}", "complete", f"Wrote {len(item.synthetic)} rows")

        emit("privacy", "running", "Checking privacy")
        relationship_metrics = evaluate_relationships(frames, synthetic_frames, context.tables)
        aggregate_metrics = evaluate_aggregate_queries(frames, synthetic_frames, context.tables)
        integrity_score, fk_score, integrity_metrics = evaluate_integrity(
            frames, synthetic_frames, context.tables
        )

        if table_reports:
            table_reports[-1].utility_metrics.extend(
                relationship_metrics + aggregate_metrics + integrity_metrics
            )

        privacy_score, utility_score, exact_overlap, direct_identifier_overlap = score_reports(
            table_reports
        )
        privacy_summary = summarize_privacy(table_reports)
        emit("privacy", "complete", f"Privacy score {privacy_score:.1f}%")

        emit("utility", "running", "Checking statistical utility")
        utility_summary = summarize_utility(table_reports)
        emit("utility", "complete", f"Utility score {utility_score:.1f}%")

        emit("relationships", "running", "Checking conditional relationships")
        emit("relationships", "complete", "Relationship metrics computed")

        emit("integrity", "running", "Checking referential integrity")
        integrity_summary = summarize_integrity(integrity_score, integrity_metrics)
        emit("integrity", "complete", f"FK integrity {fk_score:.1f}%")

        decision, reasons = render_decision(
            privacy_score,
            utility_score,
            integrity_score,
            exact_overlap,
            direct_identifier_overlap,
            privacy_summary,
            utility_summary,
            integrity_summary,
        )

        completed_at = datetime.now(UTC)
        report = RunReport(
            run_id=run_id,
            status="completed",
            asset_id=request.asset_id,
            completed_at=completed_at,
            expires_at=completed_at + timedelta(days=request.expiry_days),
            output_dir=str(output_dir),
            source_urn=context.source_urn,
            source_table_urns=[table.urn for table in context.tables],
            synthetic_urns=synthetic_urns,
            privacy_score=privacy_score,
            utility_score=utility_score,
            integrity_score=integrity_score,
            fk_integrity=fk_score,
            exact_row_overlap=exact_overlap,
            tables=table_reports,
            decision=decision,
            reasons=reasons,
            privacy_summary=privacy_summary,
            utility_summary=utility_summary,
            integrity_summary=integrity_summary,
            generation_plan={
                "seed": request.seed,
                "scale": request.scale,
                "context_source": "datahub" if settings.live_datahub else "fixture",
                "expiry_days": request.expiry_days,
                "tables": plan_tables,
                "privacy_model": (
                    "Heuristic privacy validation: direct identifier separation, exact-row "
                    "overlap checks, and non-production governance. This is not a formal "
                    "differential-privacy guarantee."
                ),
            },
            warnings=[
                "Synthetic data lowers exposure risk but does not remove the need for "
                "governance review.",
                "The included privacy tests are practical heuristics, not a mathematical "
                "privacy proof.",
            ],
        )

        if request.publish_after_generation:
            emit("publish", "running", "Publishing to DataHub")
            report.publish_result = self.publisher.publish(context, report)
            emit("publish", "complete", report.publish_result.get("status", "recorded"))

        self._write_report(report)
        self._write_readme(context.name, report)
        self._build_bundle(report)
        return report

    def get_report(self, run_id: str) -> RunReport:
        path = settings.doppel_artifact_dir / run_id / "report.json"
        if not path.exists():
            raise KeyError(run_id)
        return RunReport.model_validate_json(path.read_text())

    def list_runs(self) -> list[RunReport]:
        reports: list[RunReport] = []
        for path in settings.doppel_artifact_dir.glob("*/report.json"):
            try:
                reports.append(RunReport.model_validate_json(path.read_text()))
            except Exception:
                continue
        return sorted(reports, key=lambda item: item.created_at, reverse=True)

    def publish(self, run_id: str) -> RunReport:
        report = self.get_report(run_id)
        context = self.catalog.get_asset(report.asset_id)
        report.publish_result = self.publisher.publish(context, report)
        self._write_report(report)
        self._build_bundle(report)
        return report

    def delete(self, run_id: str) -> None:
        path = settings.doppel_artifact_dir / run_id
        if not path.exists():
            raise KeyError(run_id)
        shutil.rmtree(path)

    def _write_report(self, report: RunReport) -> None:
        Path(report.output_dir, "report.json").write_text(report.model_dump_json(indent=2))

    def _write_readme(self, asset_name: str, report: RunReport) -> None:
        content = f"""# DOPPEL synthetic data product

- Run: `{report.run_id}`
- Source: `{asset_name}`
- Decision: `{report.decision}`
- Privacy score: `{report.privacy_score}`
- Utility score: `{report.utility_score}`
- Foreign-key integrity: `{report.fk_integrity}`
- Exact source rows reproduced: `{report.exact_row_overlap}`

This bundle contains non-production synthetic data generated from DataHub-governed
context. Review `report.json` before use. The privacy score is based on explicit
heuristics and is not a formal differential-privacy guarantee.
"""
        Path(report.output_dir, "README.md").write_text(content)

    def _build_bundle(self, report: RunReport) -> Path:
        bundle = Path(report.output_dir, f"doppel-{report.run_id}.zip")
        with ZipFile(bundle, "w", ZIP_DEFLATED) as archive:
            for path in Path(report.output_dir).iterdir():
                if path == bundle or path.is_dir():
                    continue
                archive.write(path, arcname=path.name)
        return bundle


def _platform_from_dataset_urn(urn: str) -> str:
    # urn:li:dataset:(urn:li:dataPlatform:<platform>,<name>,<env>)
    if urn.startswith("urn:li:dataset:(urn:li:dataPlatform:"):
        platform_part = urn.split("urn:li:dataPlatform:", 1)[1]
        return platform_part.split(",", 1)[0]
    return settings.datahub_platform
