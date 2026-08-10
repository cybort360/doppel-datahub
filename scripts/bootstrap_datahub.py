from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from app.config import settings
from app.models import DatasetContext, SemanticType


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish DOPPEL source context to DataHub")
    parser.add_argument("--server", default=settings.datahub_gms_url)
    parser.add_argument("--token", default=settings.datahub_token)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument(
        "--asset",
        help="Asset id to bootstrap (e.g., healthcare, finance, retail). Default: all assets.",
    )
    args = parser.parse_args()

    try:
        from datahub.emitter.mce_builder import (
            make_data_platform_urn,
            make_domain_urn,
            make_tag_urn,
            make_user_urn,
        )
        from datahub.emitter.mcp import MetadataChangeProposalWrapper
        from datahub.emitter.rest_emitter import DatahubRestEmitter
        from datahub.metadata.schema_classes import (
            AuditStampClass,
            BooleanTypeClass,
            DatasetLineageTypeClass,
            DatasetPropertiesClass,
            DateTypeClass,
            DomainsClass,
            GlobalTagsClass,
            GlossaryTermAssociationClass,
            GlossaryTermsClass,
            NumberTypeClass,
            OtherSchemaClass,
            OwnerClass,
            OwnershipClass,
            OwnershipTypeClass,
            SchemaFieldClass,
            SchemaFieldDataTypeClass,
            SchemaMetadataClass,
            StringTypeClass,
            TagAssociationClass,
            TimeTypeClass,
            UpstreamClass,
            UpstreamLineageClass,
        )
    except ImportError as exc:
        raise SystemExit(
            "Install the live integration first: pip install -r requirements-datahub.txt"
        ) from exc

    data_dir = Path(settings.doppel_data_dir)
    if args.asset:
        context_paths = [data_dir / args.asset / "context.json"]
    else:
        context_paths = sorted(data_dir.glob("*/context.json"))

    contexts: list[DatasetContext] = []
    for context_path in context_paths:
        if not context_path.exists():
            raise FileNotFoundError(f"Asset context not found: {context_path}")
        contexts.append(DatasetContext.model_validate(json.loads(context_path.read_text())))

    emitter = DatahubRestEmitter(gms_server=args.server, token=args.token)
    _wait_for_datahub(emitter, timeout_sec=args.timeout)
    audit = AuditStampClass(time=int(time.time() * 1000), actor=make_user_urn("doppel"))

    # Ensure shared governance entities exist (idempotent aspect writes).
    _ensure_platform(emitter, "postgres")

    known_tags = {
        "PII",
        "PHI",
        "RESTRICTED",
        "FINANCIAL",
        "PRIMARY_KEY",
        "FOREIGN_KEY",
        "QUASI_IDENTIFIER",
    }
    for tag in known_tags:
        _ensure_tag(emitter, make_tag_urn(tag), tag)

    domain_urns: dict[str, str] = {}
    for context in contexts:
        domain_key = context.domain.lower().replace(" ", "-")
        domain_urn = make_domain_urn(domain_key)
        domain_urns[context.id] = domain_urn
        _ensure_domain(emitter, domain_urn, context.domain)

    for context in contexts:
        for table in context.tables:
            _ensure_user(emitter, make_user_urn(table.owner.lower().replace(" ", "-")))

    def field_type(semantic: SemanticType) -> Any:
        if semantic == SemanticType.NUMERIC:
            return NumberTypeClass()
        if semantic == SemanticType.BOOLEAN:
            return BooleanTypeClass()
        if semantic == SemanticType.DATE_OF_BIRTH:
            return DateTypeClass()
        if semantic == SemanticType.DATETIME:
            return TimeTypeClass()
        return StringTypeClass()

    table_by_key: dict[tuple[str, str], Any] = {}
    for context in contexts:
        domain_urn = domain_urns[context.id]
        for table in context.tables:
            urn = table.urn
            table_by_key[(context.id, table.name)] = {
                "urn": urn,
                "dataset_name": urn.rsplit(",", 2)[1],
                "table": table,
                "context": context,
                "domain_urn": domain_urn,
            }

    for context in contexts:
        domain_urn = domain_urns[context.id]
        for table in context.tables:
            info = table_by_key[(context.id, table.name)]
            urn = info["urn"]

            properties = DatasetPropertiesClass(
                name=table.name,
                description=table.description,
                customProperties={
                    "doppel_fixture": "true",
                    "doppel_source_table": table.name,
                    "doppel_source_file": table.file,
                    "primary_key": table.primary_key,
                },
            )
            tags = GlobalTagsClass(
                tags=[TagAssociationClass(tag=make_tag_urn(tag)) for tag in table.tags]
            )
            ownership = OwnershipClass(
                owners=[
                    OwnerClass(
                        owner=make_user_urn(table.owner.lower().replace(" ", "-")),
                        type=OwnershipTypeClass.TECHNICAL_OWNER,
                        source=None,
                    )
                ],
                lastModified=audit,
            )
            domains = DomainsClass(domains=[domain_urn])

        fields = []
        for column in table.columns:
            field_tags = (
                GlobalTagsClass(
                    tags=[TagAssociationClass(tag=make_tag_urn(tag)) for tag in column.tags]
                )
                if column.tags
                else None
            )

            glossary_terms = None
            if column.description:
                # Link a demo glossary term per column description; DataHub will create the
                # term entity on first bootstrap and reuse it on subsequent runs.
                term_urn = f"urn:li:glossaryTerm:doppel.{table.name}.{column.name}"
                _ensure_glossary_term(
                    emitter,
                    term_urn,
                    name=f"{table.name}.{column.name}",
                    definition=column.description,
                )
                glossary_terms = GlossaryTermsClass(
                    terms=[GlossaryTermAssociationClass(urn=term_urn)],
                    auditStamp=audit,
                )

            fields.append(
                SchemaFieldClass(
                    fieldPath=column.name,
                    nullable=column.nullable,
                    type=SchemaFieldDataTypeClass(type=field_type(column.semantic_type)),
                    nativeDataType=column.dtype,
                    description=column.description,
                    globalTags=field_tags,
                    glossaryTerms=glossary_terms,
                    lastModified=audit,
                )
            )

        from datahub.emitter.mce_builder import make_schema_field_urn
        from datahub.metadata.schema_classes import ForeignKeyConstraintClass

        schema = SchemaMetadataClass(
            schemaName=table.name,
            platform=make_data_platform_urn("postgres"),
            version=0,
            hash="",
            platformSchema=OtherSchemaClass(rawSchema=""),
            fields=fields,
            primaryKeys=[table.primary_key],
            foreignKeys=[
                ForeignKeyConstraintClass(
                    name=f"{fk.column}_to_{fk.references_table}",
                    sourceFields=[make_schema_field_urn(urn, fk.column)],
                    foreignDataset=table_by_key[(context.id, fk.references_table)]["urn"],
                    foreignFields=[
                        make_schema_field_urn(
                            table_by_key[(context.id, fk.references_table)]["urn"],
                            fk.references_column,
                        )
                    ],
                )
                for fk in table.foreign_keys
            ],
        )

        for aspect in (properties, tags, ownership, domains, schema):
            emitter.emit_mcp(MetadataChangeProposalWrapper(entityUrn=urn, aspect=aspect))
        print(f"Published source dataset {urn}")

    # Parent -> child lineage edges within each asset.
    for context in contexts:
        for table in context.tables:
            for fk in table.foreign_keys:
                child_urn = table_by_key[(context.id, table.name)]["urn"]
                parent_urn = table_by_key[(context.id, fk.references_table)]["urn"]
                lineage = UpstreamLineageClass(
                    upstreams=[
                        UpstreamClass(
                            dataset=parent_urn,
                            type=DatasetLineageTypeClass.TRANSFORMED,
                        )
                    ]
                )
                emitter.emit_mcp(
                    MetadataChangeProposalWrapper(entityUrn=child_urn, aspect=lineage)
                )
                print(f"Published lineage: {child_urn} -> {fk.references_table}")

    emitter.close()
    print("Source context is ready. Start DOPPEL with DOPPEL_MODE=datahub.")


def _wait_for_datahub(emitter: Any, timeout_sec: int = 300) -> None:
    deadline = time.time() + timeout_sec
    last_error: Exception | None = None
    gms_server = getattr(emitter, "_gms_server", "DataHub GMS")
    while time.time() < deadline:
        try:
            emitter.test_connection()
            print(f"DataHub GMS is healthy at {gms_server}")
            return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            print(f"Waiting for DataHub GMS... ({exc})")
            time.sleep(5)
    raise RuntimeError(f"DataHub GMS did not become healthy within {timeout_sec}s: {last_error}")


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


def _ensure_domain(emitter: Any, urn: str, name: str) -> None:
    from datahub.emitter.mcp import MetadataChangeProposalWrapper
    from datahub.metadata.schema_classes import DomainPropertiesClass

    emitter.emit_mcp(
        MetadataChangeProposalWrapper(
            entityUrn=urn,
            aspect=DomainPropertiesClass(name=name, description=f"{name} domain"),
        )
    )


def _ensure_tag(emitter: Any, urn: str, name: str) -> None:
    from datahub.emitter.mcp import MetadataChangeProposalWrapper
    from datahub.metadata.schema_classes import TagPropertiesClass

    emitter.emit_mcp(
        MetadataChangeProposalWrapper(
            entityUrn=urn,
            aspect=TagPropertiesClass(name=name, description=f"Governance tag: {name}"),
        )
    )


def _ensure_user(emitter: Any, urn: str) -> None:
    from datahub.emitter.mcp import MetadataChangeProposalWrapper
    from datahub.metadata.schema_classes import CorpUserInfoClass

    emitter.emit_mcp(
        MetadataChangeProposalWrapper(
            entityUrn=urn,
            aspect=CorpUserInfoClass(
                active=True,
                displayName=urn.rsplit(":", 1)[-1].replace("-", " ").title(),
            ),
        )
    )


def _ensure_glossary_term(emitter: Any, urn: str, name: str, definition: str) -> None:
    from datahub.emitter.mcp import MetadataChangeProposalWrapper
    from datahub.metadata.schema_classes import GlossaryTermInfoClass

    emitter.emit_mcp(
        MetadataChangeProposalWrapper(
            entityUrn=urn,
            aspect=GlossaryTermInfoClass(
                name=name,
                definition=definition,
                termSource="DOPPEL",
            ),
        )
    )


if __name__ == "__main__":
    main()
