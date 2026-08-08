from __future__ import annotations

import re

import pandas as pd

from app.models import ColumnContext, SemanticType

_NAME_RE = re.compile(r"(^|_)(first|last|full)?_?name$", re.I)


def infer_semantic_type(
    column: str, series: pd.Series, tags: list[str] | None = None
) -> SemanticType:
    name = column.lower()
    normalized_tags = {tag.lower() for tag in (tags or [])}

    if "foreign_key" in normalized_tags:
        return SemanticType.FOREIGN_KEY
    if "primary_key" in normalized_tags or name.endswith("_id"):
        return SemanticType.IDENTIFIER
    if "email" in name or "email" in normalized_tags:
        return SemanticType.EMAIL
    if _NAME_RE.search(name) or "person_name" in normalized_tags:
        return SemanticType.PERSON_NAME
    if name in {"dob", "date_of_birth", "birth_date"} or "date_of_birth" in normalized_tags:
        return SemanticType.DATE_OF_BIRTH
    if "postal" in name or "postcode" in name or "zip" in name:
        return SemanticType.POSTAL_CODE
    if pd.api.types.is_bool_dtype(series):
        return SemanticType.BOOLEAN
    if (
        pd.api.types.is_datetime64_any_dtype(series)
        or name.endswith("_date")
        or name.endswith("_at")
    ):
        return SemanticType.DATETIME
    if pd.api.types.is_numeric_dtype(series):
        return SemanticType.NUMERIC
    unique_ratio = series.nunique(dropna=True) / max(len(series), 1)
    if unique_ratio <= 0.15:
        return SemanticType.CATEGORICAL
    return SemanticType.FREE_TEXT


def enrich_columns(frame: pd.DataFrame, declared: list[ColumnContext]) -> list[ColumnContext]:
    by_name = {column.name: column for column in declared}
    enriched: list[ColumnContext] = []
    for name in frame.columns:
        current = by_name.get(name)
        tags = current.tags if current else []
        semantic = (
            current.semantic_type
            if current
            else infer_semantic_type(name, frame[name], tags)
        )
        enriched.append(
            ColumnContext(
                name=name,
                dtype=str(frame[name].dtype),
                semantic_type=semantic,
                nullable=bool(frame[name].isna().any()),
                tags=tags,
                description=current.description if current else "",
                strategy=current.strategy if current else "",
            )
        )
    return enriched
