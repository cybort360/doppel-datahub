from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import settings
from app.models import DatasetContext, RunReport, SemanticType


class DataHubPublisher:
    """Publishes the synthetic data product to DataHub or records an offline preview.

    Live mode uses the official acryl-datahub Python SDK. Keeping the import inside the
    method lets the demo run in fixture mode without installing the optional dependency.
    """

    def enrich_context(self, context: DatasetContext) -> DatasetContext:
        """Overlay fixture metadata with live DataHub aspects when live mode is enabled.

        The source rows remain local for a deterministic demo, while governance context comes
        from the catalog. Missing aspects are tolerated so one partially documented asset does
        not make the demo unusable.
        """
        if not settings.live_datahub:
            return context
        try:
            from datahub.ingestion.graph.client import DatahubClientConfig, DataHubGraph
            from datahub.metadata.schema_classes import (
                DatasetPropertiesClass,
                DomainsClass,
                GlobalTagsClass,
                OwnershipClass,
                SchemaMetadataClass,
            )
        except ImportError as exc:
            raise RuntimeError("Live DataHub mode requires: pip install '.[datahub]'") from exc

        graph = DataHubGraph(
            DatahubClientConfig(
                server=settings.datahub_gms_url,
                token=settings.datahub_token,
            )
        )
        enriched_tables = []
        for table in context.tables:
            updates: dict[str, Any] = {}
            try:
                properties = graph.get_aspect(table.urn, DatasetPropertiesClass)
                if properties and properties.description:
                    updates["description"] = properties.description
            except Exception:
                pass
            try:
                tag_aspect = graph.get_aspect(table.urn, GlobalTagsClass)
                if tag_aspect:
                    updates["tags"] = [
                        self._urn_to_name(association.tag) for association in tag_aspect.tags
                    ]
            except Exception:
                pass
            try:
                ownership = graph.get_aspect(table.urn, OwnershipClass)
                if ownership and ownership.owners:
                    updates["owner"] = self._urn_to_name(ownership.owners[0].owner)
            except Exception:
                pass
            try:
                domains = graph.get_aspect(table.urn, DomainsClass)
                if domains and domains.domains:
                    updates["domain"] = self._urn_to_name(domains.domains[0])
            except Exception:
                pass
            try:
                schema = graph.get_aspect(table.urn, SchemaMetadataClass)
                if schema and schema.fields:
                    live_fields = {field.fieldPath: field for field in schema.fields}
                    columns = []
                    for column in table.columns:
                        live = live_fields.get(column.name)
                        if not live:
                            columns.append(column)
                            continue
                        live_tags = []
                        global_tags = getattr(live, "globalTags", None)
                        if global_tags is not None:
                            live_tags = [
                                self._urn_to_name(association.tag)
                                for association in global_tags.tags
                            ]
                        live_terms = []
                        glossary_terms = getattr(live, "glossaryTerms", None)
                        if glossary_terms is not None:
                            live_terms = [
                                self._urn_to_name(term.urn) for term in glossary_terms.terms
                            ]
                        columns.append(
                            column.model_copy(
                                update={
                                    "description": live.description or column.description,
                                    "tags": live_tags or column.tags,
                                    "nullable": bool(live.nullable),
                                    "dtype": live.nativeDataType or column.dtype,
                                }
                            )
                        )
                        # Glossary terms are not a field on ColumnContext, but they
                        # influence governance summary so we surface them there.
                        if live_terms:
                            updates.setdefault("governance_summary", []).append(
                                f"{column.name}: linked terms {', '.join(live_terms)}"
                            )
                    updates["columns"] = columns
            except Exception:
                pass
            enriched_tables.append(table.model_copy(update=updates))
        return context.model_copy(update={"tables": enriched_tables})

    def publish(self, context: DatasetContext, report: RunReport) -> dict[str, Any]:
        if not settings.live_datahub:
            result = {
                "mode": "fixture",
                "status": "recorded",
                "message": "Offline DataHub mutation preview written to the run artifact.",
                "synthetic_urns": report.synthetic_urns,
            }
            Path(report.output_dir, "datahub-mutation-preview.json").write_text(
                json.dumps(self._mutation_preview(context, report), indent=2)
            )
            return result
        return self._publish_live(context, report)

    def _mutation_preview(self, context: DatasetContext, report: RunReport) -> dict[str, Any]:
        return {
            "source": context.source_urn,
            "synthetic_assets": [
                {
                    "urn": urn,
                    "tags": ["SYNTHETIC", "NON_PRODUCTION"],
                    "customProperties": {
                        "doppel_run_id": report.run_id,
                        "privacy_score": str(report.privacy_score),
                        "utility_score": str(report.utility_score),
                        "integrity_score": str(report.integrity_score),
                        "generated_at": (
                            report.completed_at.isoformat() if report.completed_at else ""
                        ),
                        "expires_at": (report.expires_at.isoformat() if report.expires_at else ""),
                        "source_dataset": table.urn,
                    },
                    "lineage": {"upstream": table.urn},
                }
                for table, urn in zip(context.tables, report.synthetic_urns, strict=True)
            ],
        }

    def _publish_live(self, context: DatasetContext, report: RunReport) -> dict[str, Any]:
        try:
            from datahub.emitter.mce_builder import (
                make_dataset_urn,
                make_tag_urn,
                make_user_urn,
            )
            from datahub.emitter.mcp import MetadataChangeProposalWrapper
            from datahub.emitter.rest_emitter import DatahubRestEmitter
            from datahub.metadata.schema_classes import (
                AuditStampClass,
                DatasetLineageTypeClass,
                DatasetPropertiesClass,
                GlobalTagsClass,
                InstitutionalMemoryClass,
                InstitutionalMemoryMetadataClass,
                TagAssociationClass,
                UpstreamClass,
                UpstreamLineageClass,
            )
        except ImportError as exc:
            raise RuntimeError("Live DataHub mode requires: pip install '.[datahub]'") from exc

        emitter = DatahubRestEmitter(
            gms_server=settings.datahub_gms_url,
            token=settings.datahub_token,
        )
        emitted: list[str] = []

        stamp = AuditStampClass(
            time=int(report.completed_at.timestamp() * 1000) if report.completed_at else 0,
            actor=make_user_urn("doppel"),
        )

        # Evidence is surfaced through InstitutionalMemory on each synthetic asset.
        # DataHub's standalone Document entity is not enabled in all quickstart
        # deployments, so we use the supported dataset-level documentation link.
        report_path = Path(report.output_dir, "report.json")
        report_text = report.model_dump_json(indent=2)
        if len(report_text) > 50_000:
            report_text = report_text[:50_000] + "\n... [truncated]"

        source_urn_to_synthetic_urn = {
            table.urn: synthetic_urn
            for table, synthetic_urn in zip(context.tables, report.synthetic_urns, strict=True)
        }
        table_name_to_source_urn = {table.name: table.urn for table in context.tables}

        for table, synthetic_urn in zip(context.tables, report.synthetic_urns, strict=True):
            source_platform = self._platform_from_dataset_urn(table.urn)
            self._ensure_platform(emitter, source_platform)

            dataset_name = synthetic_urn.split(",")[1]
            urn = make_dataset_urn(
                platform=source_platform,
                name=dataset_name,
                env=settings.doppel_target_env,
            )
            generated_at = report.completed_at.isoformat() if report.completed_at else ""
            expires_at = report.expires_at.isoformat() if report.expires_at else ""
            properties = DatasetPropertiesClass(
                name=f"{table.name}_synthetic",
                description=(
                    f"Synthetic, non-production twin of `{table.urn}` generated by DOPPEL. "
                    "This asset is intended for development and testing, not production decisions."
                ),
                customProperties={
                    "doppel_run_id": report.run_id,
                    "privacy_score": str(report.privacy_score),
                    "utility_score": str(report.utility_score),
                    "integrity_score": str(report.integrity_score),
                    "fk_integrity": str(report.fk_integrity),
                    "exact_row_overlap": str(report.exact_row_overlap),
                    "generated_at": generated_at,
                    "expires_at": expires_at,
                    "expires_in_days": str(report.generation_plan["expiry_days"]),
                    "source_dataset": table.urn,
                    "source_asset": context.source_urn,
                    "synthetic_generation_strategy": "metadata_governed",
                },
            )
            tags = GlobalTagsClass(
                tags=[
                    TagAssociationClass(tag=make_tag_urn(tag))
                    for tag in ["SYNTHETIC", "NON_PRODUCTION"]
                ]
            )
            lineage = UpstreamLineageClass(
                upstreams=[
                    UpstreamClass(
                        dataset=table.urn,
                        type=DatasetLineageTypeClass.TRANSFORMED,
                    )
                ]
            )
            evidence = InstitutionalMemoryClass(
                elements=[
                    InstitutionalMemoryMetadataClass(
                        url=f"file://{report_path.resolve()}",
                        description=(
                            f"DOPPEL evidence report for run {report.run_id}. "
                            f"Privacy {report.privacy_score}, utility {report.utility_score}, "
                            f"integrity {report.integrity_score}."
                        ),
                        createStamp=stamp,
                    )
                ]
            )
            schema = self._schema_for_table(
                table,
                dataset_urn=urn,
                table_name_to_source_urn=table_name_to_source_urn,
                source_urn_to_synthetic_urn=source_urn_to_synthetic_urn,
            )
            for aspect in (properties, tags, lineage, evidence, schema):
                emitter.emit_mcp(MetadataChangeProposalWrapper(entityUrn=urn, aspect=aspect))
            emitted.append(urn)
        emitter.close()
        return {"mode": "datahub", "status": "published", "emitted": emitted}

    @staticmethod
    def _ensure_platform(emitter: Any, platform: str) -> None:
        from datahub.emitter.mce_builder import make_data_platform_urn
        from datahub.emitter.mcp import MetadataChangeProposalWrapper
        from datahub.metadata.schema_classes import DataPlatformInfoClass

        emitter.emit_mcp(
            MetadataChangeProposalWrapper(
                entityUrn=make_data_platform_urn(platform),
                aspect=DataPlatformInfoClass(
                    name=platform,
                    type="RELATIONAL_DB",
                    datasetNameDelimiter=".",
                ),
            )
        )

    @staticmethod
    def _platform_from_dataset_urn(urn: str) -> str:
        # urn:li:dataset:(urn:li:dataPlatform:<platform>,<name>,<env>)
        if urn.startswith("urn:li:dataset:(urn:li:dataPlatform:"):
            platform_part = urn.split("urn:li:dataPlatform:", 1)[1]
            return platform_part.split(",", 1)[0]
        return settings.datahub_platform

    def _schema_for_table(
        self,
        table: Any,
        dataset_urn: str,
        table_name_to_source_urn: dict[str, str],
        source_urn_to_synthetic_urn: dict[str, str],
    ) -> Any:
        from datahub.emitter.mce_builder import make_data_platform_urn, make_schema_field_urn
        from datahub.metadata.schema_classes import (
            ForeignKeyConstraintClass,
            OtherSchemaClass,
            SchemaFieldClass,
            SchemaFieldDataTypeClass,
            SchemaMetadataClass,
        )

        source_platform = self._platform_from_dataset_urn(dataset_urn)
        platform_urn = make_data_platform_urn(source_platform)

        fields = [
            SchemaFieldClass(
                fieldPath=column.name,
                nullable=column.nullable,
                type=SchemaFieldDataTypeClass(type=self._schema_field_type(column.semantic_type)),
                nativeDataType=column.dtype,
                description=column.description,
            )
            for column in table.columns
        ]

        foreign_keys = []
        for fk in table.foreign_keys:
            parent_source_urn = table_name_to_source_urn.get(fk.references_table)
            parent_synthetic_urn = (
                source_urn_to_synthetic_urn.get(parent_source_urn) if parent_source_urn else None
            )
            if parent_synthetic_urn:
                foreign_keys.append(
                    ForeignKeyConstraintClass(
                        name=f"{fk.column}_to_{fk.references_table}",
                        sourceFields=[make_schema_field_urn(dataset_urn, fk.column)],
                        foreignDataset=parent_synthetic_urn,
                        foreignFields=[
                            make_schema_field_urn(parent_synthetic_urn, fk.references_column)
                        ],
                    )
                )

        return SchemaMetadataClass(
            schemaName=f"{table.name}_synthetic",
            platform=platform_urn,
            version=0,
            hash="",
            platformSchema=OtherSchemaClass(rawSchema=""),
            fields=fields,
            primaryKeys=[table.primary_key],
            foreignKeys=foreign_keys,
        )

    @staticmethod
    def _schema_field_type(semantic: SemanticType) -> Any:
        from datahub.metadata.schema_classes import (
            BooleanTypeClass,
            DateTypeClass,
            NumberTypeClass,
            StringTypeClass,
            TimeTypeClass,
        )

        if semantic == SemanticType.NUMERIC:
            return NumberTypeClass()
        if semantic == SemanticType.BOOLEAN:
            return BooleanTypeClass()
        if semantic == SemanticType.DATETIME:
            return TimeTypeClass()
        if semantic == SemanticType.DATE_OF_BIRTH:
            return DateTypeClass()
        return StringTypeClass()

    @staticmethod
    def _urn_to_name(urn: str) -> str:
        return urn.rsplit(":", 1)[-1] if ":" in urn else urn
