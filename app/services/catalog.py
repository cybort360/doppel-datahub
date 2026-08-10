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

    def list_assets(self) -> list[DatasetContext]:
        assets: list[DatasetContext] = []
        for context_path in sorted(self.data_dir.glob("*/context.json")):
            assets.append(DatasetContext.model_validate(json.loads(context_path.read_text())))
        if not assets:
            raise RuntimeError(f"No asset contexts found under {self.data_dir}")
        return assets

    def get_asset(self, asset_id: str) -> DatasetContext:
        context_path = self.data_dir / asset_id / "context.json"
        if not context_path.exists():
            raise KeyError(f"Unknown asset: {asset_id}")
        if settings.live_datahub:
            return self._load_from_datahub(asset_id)
        payload = json.loads(context_path.read_text())
        return DatasetContext.model_validate(payload)

    def _load_from_datahub(self, asset_id: str) -> DatasetContext:
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

        # Start from the fixture context so asset-level metadata and source URNs
        # are stable even when reading live DataHub metadata.
        context_path = self.data_dir / asset_id / "context.json"
        base_context = DatasetContext.model_validate(json.loads(context_path.read_text()))

        tables: list[TableContext] = []
        for table in base_context.tables:
            tables.append(self._table_from_datahub(graph, table))

        parent_urn = base_context.source_urn
        name = base_context.name
        description = base_context.description
        domain = base_context.domain
        owner = base_context.owner

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
            id=asset_id,
            name=name,
            description=description,
            domain=domain,
            owner=owner,
            source_urn=parent_urn,
            tables=tables,
            governance_summary=base_context.governance_summary,
        )

    def _table_from_datahub(self, graph: Any, base: TableContext) -> TableContext:
        from datahub.metadata.schema_classes import (
            DatasetPropertiesClass,
            DomainsClass,
            GlobalTagsClass,
            OwnershipClass,
            SchemaMetadataClass,
        )

        urn = base.urn
        dataset_name = base.name
        source_file = base.file

        properties = graph.get_aspect(urn, DatasetPropertiesClass)
        if properties:
            if properties.customProperties:
                source_file = properties.customProperties.get("doppel_source_file", source_file)
            if properties.description:
                base.description = properties.description

        tags: list[str] = []
        try:
            tag_aspect = graph.get_aspect(urn, GlobalTagsClass)
            if tag_aspect:
                tags = [self._urn_to_name(association.tag) for association in tag_aspect.tags]
        except Exception:
            pass

        domain = base.domain
        try:
            domains = graph.get_aspect(urn, DomainsClass)
            if domains and domains.domains:
                domain = self._urn_to_name(domains.domains[0])
        except Exception:
            pass

        owner = base.owner
        try:
            ownership = graph.get_aspect(urn, OwnershipClass)
            if ownership and ownership.owners:
                owner = self._urn_to_name(ownership.owners[0].owner)
        except Exception:
            pass

        schema = graph.get_aspect(urn, SchemaMetadataClass)
        columns: list[ColumnContext] = []
        primary_key = base.primary_key
        foreign_keys: list[ForeignKey] = base.foreign_keys.copy()

        if schema and schema.fields:
            primary_key = (schema.primaryKeys or [primary_key or None])[0] or primary_key
            for field in schema.fields:
                columns.append(self._column_from_field(field, primary_key))

            datahub_fks: list[ForeignKey] = []
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

                datahub_fks.append(
                    ForeignKey(
                        column=source_field,
                        references_table=self._dataset_urn_to_name(fk.foreignDataset),
                        references_column=foreign_field,
                    )
                )
            if datahub_fks:
                foreign_keys = datahub_fks

        # Fallback: infer foreign keys from column names when DataHub does not
        # materialize SchemaMetadata.foreignKeys.
        if not foreign_keys:
            foreign_keys = self._infer_foreign_keys(columns, dataset_name)

        return TableContext(
            name=dataset_name,
            file=source_file,
            urn=urn,
            description=base.description,
            domain=domain,
            owner=owner,
            tags=tags or base.tags,
            primary_key=primary_key,
            foreign_keys=foreign_keys,
            columns=columns or base.columns,
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
        if "PHONE" in hints or "phone" in name or "mobile" in name:
            return SemanticType.DIRECT_IDENTIFIER
        if "ADDRESS" in hints or "address" in name or "street" in name:
            return SemanticType.DIRECT_IDENTIFIER
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
            # Conditional generation can be declared explicitly in fixture contexts.
            # In live DataHub mode we preserve the known healthcare conditional.
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
            # Heuristic: a column like customer_id references customers.customer_id.
            prefix = column.name.replace("_id", "")
            candidate_tables = [f"{prefix}s", prefix]
            for candidate in candidate_tables:
                if candidate and candidate != table_name:
                    fks.append(
                        ForeignKey(
                            column=column.name,
                            references_table=candidate,
                            references_column=column.name,
                        )
                    )
                    break
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
