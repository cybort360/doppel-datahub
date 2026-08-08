from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import settings
from app.models import ColumnContext, DatasetContext, ForeignKey, SemanticType, TableContext

try:
    from datahub.ingestion.graph.client import DataHubGraph
except ImportError:
    DataHubGraph = None  # type: ignore[misc,assignment]


class CatalogService:
    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir or settings.doppel_data_dir
        self._context_path = self.data_dir / "context.json"

    def list_assets(self) -> list[DatasetContext]:
        return [self.get_asset("healthcare")]

    def get_asset(self, asset_id: str) -> DatasetContext:
        if asset_id != "healthcare":
            raise KeyError(f"Unknown asset: {asset_id}")
        if settings.live_datahub:
            return self._load_from_datahub()
        payload = json.loads(self._context_path.read_text())
        return DatasetContext.model_validate(payload)

    def _load_from_datahub(self) -> DatasetContext:
        if DataHubGraph is None:
            raise RuntimeError("Live DataHub mode requires: pip install '.[datahub]'")

        from datahub.ingestion.graph.client import DatahubClientConfig
        from datahub.metadata.schema_classes import (
            DatasetPropertiesClass,
            DomainsClass,
            OwnershipClass,
        )

        graph = DataHubGraph(
            DatahubClientConfig(
                server=settings.datahub_gms_url,
                token=settings.datahub_token,
            )
        )

        tables: list[TableContext] = []
        for urn in settings.source_dataset_urns:
            table = self._table_from_datahub(graph, urn)
            tables.append(table)

        # Use the first source dataset as the parent asset metadata source.
        parent_urn = settings.source_dataset_urns[0]
        name = "Clinical Operations Twin"
        description = (
            "Synthetic patient and encounter data for privacy-safe development and testing."
        )
        domain = "Clinical Operations"
        owner = "Data Platform Team"

        properties = graph.get_aspect(parent_urn, DatasetPropertiesClass)
        if properties:
            name = properties.name or name
            description = properties.description or description

        domains = graph.get_aspect(parent_urn, DomainsClass)
        if domains and domains.domains:
            domain = self._urn_to_name(domains.domains[0])

        ownership = graph.get_aspect(parent_urn, OwnershipClass)
        if ownership and ownership.owners:
            owner = self._urn_to_name(ownership.owners[0].owner)

        return DatasetContext(
            id="healthcare",
            name=name,
            description=description,
            domain=domain,
            owner=owner,
            source_urn=parent_urn,
            tables=tables,
            governance_summary=[
                "Direct identifiers are tagged and must never be copied.",
                "Patient-to-encounter relationships must remain valid.",
                "Generated assets expire after a declared non-production window.",
                "Aggregate distributions should remain useful for product testing.",
            ],
        )

    def _table_from_datahub(self, graph: Any, urn: str) -> TableContext:
        from datahub.metadata.schema_classes import (
            DatasetPropertiesClass,
            DomainsClass,
            GlobalTagsClass,
            OwnershipClass,
            SchemaMetadataClass,
        )

        dataset_name = self._dataset_urn_to_name(urn)

        # Source file mapping: bootstrap stores the local fixture filename so DOPPEL
        # can read source values even when metadata is served by DataHub.
        source_file = f"{dataset_name}.csv"
        properties = graph.get_aspect(urn, DatasetPropertiesClass)
        if properties and properties.customProperties:
            source_file = properties.customProperties.get("doppel_source_file", source_file)

        description = ""
        if properties and properties.description:
            description = properties.description

        tags: list[str] = []
        try:
            tag_aspect = graph.get_aspect(urn, GlobalTagsClass)
            if tag_aspect:
                tags = [self._urn_to_name(association.tag) for association in tag_aspect.tags]
        except Exception:
            pass

        domain = ""
        try:
            domains = graph.get_aspect(urn, DomainsClass)
            if domains and domains.domains:
                domain = self._urn_to_name(domains.domains[0])
        except Exception:
            pass

        owner = ""
        try:
            ownership = graph.get_aspect(urn, OwnershipClass)
            if ownership and ownership.owners:
                owner = self._urn_to_name(ownership.owners[0].owner)
        except Exception:
            pass

        schema = graph.get_aspect(urn, SchemaMetadataClass)
        columns: list[ColumnContext] = []
        primary_key = ""
        foreign_keys: list[ForeignKey] = []

        if schema and schema.fields:
            primary_key = (schema.primaryKeys or [None])[0] or ""
            for field in schema.fields:
                columns.append(self._column_from_field(field, primary_key))

            for fk in schema.foreignKeys or []:
                from datahub.emitter.mce_builder import schema_field_urn_to_key

                def _field_value(field_ref: str) -> str:
                    if field_ref.startswith("urn:li:schemaField:"):
                        key = schema_field_urn_to_key(field_ref)
                        return key.fieldPath if key is not None else field_ref
                    return field_ref

                source_fields = getattr(fk, "sourceFields", None)
                if isinstance(source_fields, list) and source_fields:
                    source_field = _field_value(source_fields[0])
                else:
                    source_field = getattr(fk, "fieldPath", "")

                foreign_fields = getattr(fk, "foreignFields", None)
                if isinstance(foreign_fields, list) and foreign_fields:
                    foreign_field = _field_value(foreign_fields[0])
                else:
                    foreign_field = ""

                foreign_keys.append(
                    ForeignKey(
                        column=source_field,
                        references_table=self._dataset_urn_to_name(fk.foreignDataset),
                        references_column=foreign_field,
                    )
                )

        # Fallback: infer foreign keys from column names when DataHub does not
        # materialize SchemaMetadata.foreignKeys.
        if not foreign_keys:
            foreign_keys = self._infer_foreign_keys(columns, dataset_name)

        return TableContext(
            name=dataset_name,
            file=source_file,
            urn=urn,
            description=description,
            domain=domain,
            owner=owner,
            tags=tags,
            primary_key=primary_key,
            foreign_keys=foreign_keys,
            columns=columns,
        )

    def _column_from_field(self, field: Any, table_primary_key: str) -> ColumnContext:

        tags: list[str] = []
        if getattr(field, "globalTags", None):
            tags = [self._urn_to_name(association.tag) for association in field.globalTags.tags]

        term_hints: list[str] = []
        if getattr(field, "glossaryTerms", None):
            term_hints = [self._urn_to_name(term.urn) for term in field.glossaryTerms.terms]

        dtype = field.nativeDataType or "object"
        semantic = self._infer_semantic_type(field, tags, table_primary_key, term_hints)
        strategy = self._strategy_for_semantic(semantic, field.fieldPath)

        description = getattr(field, "description", "") or ""
        if term_hints and not description:
            description = f"Glossary terms: {', '.join(term_hints)}"

        return ColumnContext(
            name=field.fieldPath,
            dtype=dtype,
            semantic_type=semantic,
            nullable=bool(getattr(field, "nullable", True)),
            tags=tags,
            description=description,
            strategy=strategy,
        )

    def _infer_semantic_type(
        self,
        field: Any,
        tags: list[str],
        table_primary_key: str,
        term_hints: list[str] | None = None,
    ) -> SemanticType:
        from datahub.metadata.schema_classes import (
            BooleanTypeClass,
            DateTypeClass,
            NumberTypeClass,
            TimeTypeClass,
        )

        name = field.fieldPath.lower()
        tag_set = {tag.upper() for tag in tags}
        term_set = {term.upper() for term in (term_hints or [])}
        hints = tag_set | term_set
        type_class = type(field.type.type) if getattr(field, "type", None) else None

        if name == table_primary_key:
            return SemanticType.IDENTIFIER
        if "FOREIGN_KEY" in hints or name.endswith("_id") and name != table_primary_key:
            return SemanticType.FOREIGN_KEY
        if "EMAIL" in hints or "email" in name:
            return SemanticType.EMAIL
        if ("PII" in hints or "PERSON_NAME" in term_set) and (
            "name" in name or "first" in name or "last" in name
        ):
            return SemanticType.PERSON_NAME
        if name == "date_of_birth" or "DOB" in hints or "BIRTH" in hints:
            return SemanticType.DATE_OF_BIRTH
        if type_class is DateTypeClass or type_class is TimeTypeClass or "date" in name:
            return SemanticType.DATETIME
        if "POSTAL" in hints or "postal" in name or "zip" in name:
            return SemanticType.POSTAL_CODE
        if type_class is NumberTypeClass:
            return SemanticType.NUMERIC
        if type_class is BooleanTypeClass:
            return SemanticType.BOOLEAN
        if "CATEGORICAL" in hints:
            return SemanticType.CATEGORICAL
        return SemanticType.CATEGORICAL

    def _strategy_for_semantic(self, semantic: SemanticType, column_name: str) -> str:
        if semantic == SemanticType.IDENTIFIER:
            return "surrogate_id"
        if semantic == SemanticType.FOREIGN_KEY:
            return "frequency_preserving_fk"
        if semantic == SemanticType.EMAIL:
            return "reserved_domain_email"
        if semantic == SemanticType.PERSON_NAME:
            return "faker_name"
        if semantic == SemanticType.DATE_OF_BIRTH:
            return "distribution_preserving_date"
        if semantic == SemanticType.DATETIME:
            return "distribution_preserving_date"
        if semantic == SemanticType.POSTAL_CODE:
            return "faker_postcode"
        if semantic == SemanticType.NUMERIC:
            if column_name == "claim_amount":
                return "conditional_on:procedure_code"
            return "gaussian_copula"
        if semantic == SemanticType.CATEGORICAL:
            return "categorical_distribution"
        if semantic == SemanticType.BOOLEAN:
            return "categorical_distribution"
        return semantic.value

    def _infer_foreign_keys(
        self, columns: list[ColumnContext], table_name: str
    ) -> list[ForeignKey]:
        fks: list[ForeignKey] = []
        for column in columns:
            if column.semantic_type != SemanticType.FOREIGN_KEY:
                continue
            # Patient/encounter demo: patient_id references patients.patient_id.
            if column.name == "patient_id" and table_name == "encounters":
                fks.append(
                    ForeignKey(
                        column="patient_id",
                        references_table="patients",
                        references_column="patient_id",
                    )
                )
        return fks

    @staticmethod
    def _urn_to_name(urn: str) -> str:
        return urn.rsplit(":", 1)[-1] if ":" in urn else urn

    @staticmethod
    def _dataset_urn_to_name(urn: str) -> str:
        # urn:li:dataset:(urn:li:dataPlatform:<platform>,<name>,<env>)
        if "," in urn:
            name = urn.rsplit(",", 2)[1]
            return name.rsplit(".", 1)[-1]
        return urn.rsplit(":", 1)[-1] if ":" in urn else urn
