from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class SemanticType(StrEnum):
    IDENTIFIER = "identifier"
    FOREIGN_KEY = "foreign_key"
    EMAIL = "email"
    PERSON_NAME = "person_name"
    DATE_OF_BIRTH = "date_of_birth"
    POSTAL_CODE = "postal_code"
    DATETIME = "datetime"
    CATEGORICAL = "categorical"
    NUMERIC = "numeric"
    BOOLEAN = "boolean"
    FREE_TEXT = "free_text"


class ColumnContext(BaseModel):
    name: str
    dtype: str
    semantic_type: SemanticType
    nullable: bool = True
    tags: list[str] = Field(default_factory=list)
    description: str = ""
    strategy: str = ""


class ForeignKey(BaseModel):
    column: str
    references_table: str
    references_column: str


class TableContext(BaseModel):
    name: str
    file: str
    urn: str
    description: str
    domain: str
    owner: str
    tags: list[str]
    primary_key: str
    foreign_keys: list[ForeignKey] = Field(default_factory=list)
    columns: list[ColumnContext]


class DatasetContext(BaseModel):
    id: str
    name: str
    description: str
    domain: str
    owner: str
    source_urn: str
    tables: list[TableContext]
    governance_summary: list[str] = Field(default_factory=list)


class GenerateRequest(BaseModel):
    asset_id: str = "healthcare"
    scale: float = Field(default=1.0, ge=0.1, le=5.0)
    seed: int = Field(default=42, ge=0, le=2_147_483_647)
    expiry_days: int = Field(default=30, ge=1, le=365)
    publish_after_generation: bool = False


class Metric(BaseModel):
    name: str
    value: float | int | str
    status: str
    detail: str


class TableReport(BaseModel):
    table: str
    source_rows: int
    synthetic_rows: int
    privacy_metrics: list[Metric]
    utility_metrics: list[Metric]


class RunReport(BaseModel):
    run_id: str
    status: str
    asset_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    expires_at: datetime | None = None
    output_dir: str
    source_urn: str
    source_table_urns: list[str] = Field(default_factory=list)
    synthetic_urns: list[str] = Field(default_factory=list)
    privacy_score: float = 0
    utility_score: float = 0
    integrity_score: float = 0
    fk_integrity: float = 0
    exact_row_overlap: int = 0
    tables: list[TableReport] = Field(default_factory=list)
    generation_plan: dict[str, Any] = Field(default_factory=dict)
    publish_result: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)
    decision: str = "REJECTED"
    reasons: list[str] = Field(default_factory=list)
    privacy_summary: dict[str, Any] = Field(default_factory=dict)
    utility_summary: dict[str, Any] = Field(default_factory=dict)
    integrity_summary: dict[str, Any] = Field(default_factory=dict)
