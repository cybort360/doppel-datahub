from __future__ import annotations

import hashlib
from collections.abc import Iterable
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import ks_2samp

from app.models import Metric, SemanticType, TableContext, TableReport

# ---------------------------------------------------------------------------
# Verification thresholds
# ---------------------------------------------------------------------------
# These are pragmatic engineering thresholds, not statistical proofs.
PRIVACY_SCORE_THRESHOLD = 100.0
INTEGRITY_SCORE_THRESHOLD = 100.0
UTILITY_SCORE_THRESHOLD = 70.0

SINGLING_OUT_GOOD = 0.10
SINGLING_OUT_WARN = 0.25

NULL_DELTA_GOOD = 0.02
NULL_DELTA_WARN = 0.08

NUMERIC_DISTRIBUTION_GOOD = 0.85
NUMERIC_DISTRIBUTION_WARN = 0.70
CATEGORICAL_DISTRIBUTION_GOOD = 0.90
CATEGORICAL_DISTRIBUTION_WARN = 0.75
DATE_DISTRIBUTION_GOOD = 0.85
DATE_DISTRIBUTION_WARN = 0.70
CORRELATION_GOOD = 0.90
CORRELATION_WARN = 0.75
CONDITIONAL_GOOD = 0.90
CONDITIONAL_WARN = 0.75
CARDINALITY_GOOD = 0.85
CARDINALITY_WARN = 0.70
RELATIONSHIP_GOOD = 0.80
RELATIONSHIP_WARN = 0.65
AGGREGATE_QUERY_GOOD = 0.80
AGGREGATE_QUERY_WARN = 0.65


def _hash_rows(frame: pd.DataFrame) -> set[str]:
    normalized = frame.fillna("<NULL>").astype(str).agg("|".join, axis=1)
    return {hashlib.sha256(value.encode()).hexdigest() for value in normalized}


def _status(value: float, good: float, warn: float, higher_is_better: bool = True) -> str:
    if higher_is_better:
        return "pass" if value >= good else "warn" if value >= warn else "fail"
    return "pass" if value <= good else "warn" if value <= warn else "fail"


def _categorical_similarity(left: pd.Series, right: pd.Series) -> float:
    left_counts = left.fillna("<NULL>").astype(str).value_counts(normalize=True)
    right_counts = right.fillna("<NULL>").astype(str).value_counts(normalize=True)
    categories = left_counts.index.union(right_counts.index)
    tvd = 0.5 * float(
        (
            left_counts.reindex(categories, fill_value=0)
            - right_counts.reindex(categories, fill_value=0)
        )
        .abs()
        .sum()
    )
    return 1.0 - tvd


def evaluate_table(
    table: TableContext, source: pd.DataFrame, synthetic: pd.DataFrame
) -> TableReport:
    columns = {column.name: column for column in table.columns}
    overlap = len(_hash_rows(source) & _hash_rows(synthetic))
    direct_identifier_overlap = 0
    identifier_columns: list[str] = []

    for name, column in columns.items():
        if column.semantic_type in {
            SemanticType.IDENTIFIER,
            SemanticType.EMAIL,
            SemanticType.PERSON_NAME,
            SemanticType.POSTAL_CODE,
        }:
            identifier_columns.append(name)
            original = set(source[name].dropna().astype(str))
            generated = set(synthetic[name].dropna().astype(str))
            direct_identifier_overlap += len(original & generated)

    privacy_metrics = [
        Metric(
            name="exact_row_overlap",
            value=overlap,
            status="pass" if overlap == 0 else "fail",
            detail="Number of complete source rows reproduced in the synthetic table.",
        ),
        Metric(
            name="direct_identifier_overlap",
            value=direct_identifier_overlap,
            status="pass" if direct_identifier_overlap == 0 else "fail",
            detail=(
                f"Value overlap across direct-identifier fields: "
                f"{', '.join(identifier_columns)}."
            ),
        ),
    ]

    quasi_columns = [
        name
        for name, column in columns.items()
        if any(tag.upper() == "QUASI_IDENTIFIER" for tag in column.tags)
    ]
    if quasi_columns:
        # Singling-out metric: generalize each quasi-identifier (decade for dates,
        # 3-character prefix for postal codes, raw otherwise), then measure the
        # fraction of synthetic rows that land in a generalized group with fewer
        # than five members.
        generalized = pd.DataFrame(index=synthetic.index)
        for name in quasi_columns:
            column = columns[name]
            if column.semantic_type in {SemanticType.DATE_OF_BIRTH, SemanticType.DATETIME}:
                years = pd.to_datetime(synthetic[name], errors="coerce").dt.year
                generalized[name] = (years // 10 * 10).fillna(-1).astype(int).astype(str)
            elif column.semantic_type == SemanticType.POSTAL_CODE:
                generalized[name] = synthetic[name].fillna("<NULL>").astype(str).str[:3]
            else:
                generalized[name] = synthetic[name].fillna("<NULL>").astype(str)
        class_sizes = generalized.groupby(quasi_columns, dropna=False)[quasi_columns[0]].transform(
            "size"
        )
        singling_out_rate = float((class_sizes < 5).mean())
        privacy_metrics.append(
            Metric(
                name="quasi_identifier_singling_out_rate",
                value=round(singling_out_rate, 4),
                status=_status(
                    singling_out_rate, SINGLING_OUT_GOOD, SINGLING_OUT_WARN, higher_is_better=False
                ),
                detail=(
                    "Fraction of rows in generalized quasi-identifier groups smaller than five. "
                    "Dates are generalized to decade and postal codes to prefix."
                ),
            )
        )

    utility_metrics: list[Metric] = []
    null_deltas: list[float] = []
    similarity_scores: list[float] = []

    for name, column in columns.items():
        source_null = float(source[name].isna().mean())
        synthetic_null = float(synthetic[name].isna().mean())
        null_deltas.append(abs(source_null - synthetic_null))

        if column.semantic_type == SemanticType.NUMERIC:
            left = pd.to_numeric(source[name], errors="coerce").dropna()
            right = pd.to_numeric(synthetic[name], errors="coerce").dropna()
            score = (
                1.0 if left.empty or right.empty else 1.0 - float(ks_2samp(left, right).statistic)
            )
            similarity_scores.append(score)
            utility_metrics.append(
                Metric(
                    name=f"distribution:{name}",
                    value=round(score, 4),
                    status=_status(score, NUMERIC_DISTRIBUTION_GOOD, NUMERIC_DISTRIBUTION_WARN),
                    detail=(
                        "One minus the Kolmogorov-Smirnov distance for the "
                        "numerical distribution."
                    ),
                )
            )
        elif column.semantic_type in {SemanticType.CATEGORICAL, SemanticType.BOOLEAN}:
            score = _categorical_similarity(source[name], synthetic[name])
            similarity_scores.append(score)
            utility_metrics.append(
                Metric(
                    name=f"distribution:{name}",
                    value=round(score, 4),
                    status=_status(
                        score, CATEGORICAL_DISTRIBUTION_GOOD, CATEGORICAL_DISTRIBUTION_WARN
                    ),
                    detail="One minus total-variation distance for the categorical distribution.",
                )
            )
        elif column.semantic_type in {SemanticType.DATE_OF_BIRTH, SemanticType.DATETIME}:
            left = pd.to_datetime(source[name], errors="coerce").dropna().astype("int64")
            right = pd.to_datetime(synthetic[name], errors="coerce").dropna().astype("int64")
            score = (
                1.0 if left.empty or right.empty else 1.0 - float(ks_2samp(left, right).statistic)
            )
            similarity_scores.append(score)
            utility_metrics.append(
                Metric(
                    name=f"date_distribution:{name}",
                    value=round(score, 4),
                    status=_status(score, DATE_DISTRIBUTION_GOOD, DATE_DISTRIBUTION_WARN),
                    detail="One minus the Kolmogorov-Smirnov distance over parsed timestamps.",
                )
            )

    numeric_names = [
        name for name, column in columns.items() if column.semantic_type == SemanticType.NUMERIC
    ]
    if len(numeric_names) >= 2:
        source_corr = source[numeric_names].apply(pd.to_numeric, errors="coerce").corr().to_numpy()
        synthetic_corr = (
            synthetic[numeric_names].apply(pd.to_numeric, errors="coerce").corr().to_numpy()
        )
        mask = np.triu(np.ones_like(source_corr, dtype=bool), k=1)
        difference = float(np.nanmean(np.abs(source_corr[mask] - synthetic_corr[mask])))
        correlation_score = 1.0 - min(difference / 2.0, 1.0)
        utility_metrics.append(
            Metric(
                name="correlation_similarity",
                value=round(correlation_score, 4),
                status=_status(correlation_score, CORRELATION_GOOD, CORRELATION_WARN),
                detail="Similarity of pairwise numerical correlations.",
            )
        )

    for name, column in columns.items():
        if column.semantic_type != SemanticType.NUMERIC or not column.strategy.startswith(
            "conditional_on:"
        ):
            continue
        condition = column.strategy.split(":", 1)[1]
        source_means = (
            source.assign(**{name: pd.to_numeric(source[name], errors="coerce")})
            .groupby(condition)[name]
            .mean()
        )
        synthetic_means = (
            synthetic.assign(**{name: pd.to_numeric(synthetic[name], errors="coerce")})
            .groupby(condition)[name]
            .mean()
        )
        groups = source_means.index.union(synthetic_means.index)
        left = source_means.reindex(groups)
        right = synthetic_means.reindex(groups)
        mean_error = float((left - right).abs().mean())
        scale = max(float(pd.to_numeric(source[name], errors="coerce").abs().mean()), 1e-9)
        conditional_score = 1.0 - min(mean_error / scale, 1.0)
        utility_metrics.append(
            Metric(
                name=f"conditional_mean:{name}|{condition}",
                value=round(conditional_score, 4),
                status=_status(conditional_score, CONDITIONAL_GOOD, CONDITIONAL_WARN),
                detail=f"Similarity of {name} means within each {condition} group.",
            )
        )

    mean_null_delta = float(np.mean(null_deltas)) if null_deltas else 0.0
    utility_metrics.insert(
        0,
        Metric(
            name="mean_null_rate_delta",
            value=round(mean_null_delta, 4),
            status=_status(
                mean_null_delta, NULL_DELTA_GOOD, NULL_DELTA_WARN, higher_is_better=False
            ),
            detail="Mean absolute difference between source and synthetic null rates.",
        ),
    )
    utility_metrics.insert(
        0,
        Metric(
            name="schema_match",
            value=1.0 if list(source.columns) == list(synthetic.columns) else 0.0,
            status="pass" if list(source.columns) == list(synthetic.columns) else "fail",
            detail="Column names and ordering are preserved.",
        ),
    )

    return TableReport(
        table=table.name,
        source_rows=len(source),
        synthetic_rows=len(synthetic),
        privacy_metrics=privacy_metrics,
        utility_metrics=utility_metrics,
    )


def score_reports(reports: Iterable[TableReport]) -> tuple[float, float, int, int]:
    reports = list(reports)
    exact_overlap = sum(
        int(metric.value)
        for report in reports
        for metric in report.privacy_metrics
        if metric.name == "exact_row_overlap"
    )
    direct_identifier_overlap = sum(
        int(metric.value)
        for report in reports
        for metric in report.privacy_metrics
        if metric.name == "direct_identifier_overlap"
    )
    privacy_checks = [
        metric.status == "pass" for report in reports for metric in report.privacy_metrics
    ]
    utility_values = [
        float(metric.value)
        for report in reports
        for metric in report.utility_metrics
        if metric.name == "schema_match"
        or metric.name.startswith("distribution:")
        or metric.name.startswith("date_distribution:")
        or metric.name.startswith("conditional_mean:")
        or metric.name == "correlation_similarity"
    ]
    privacy_score = 100.0 * (sum(privacy_checks) / max(len(privacy_checks), 1))
    utility_score = 100.0 * (sum(utility_values) / max(len(utility_values), 1))
    return (
        round(privacy_score, 1),
        round(utility_score, 1),
        exact_overlap,
        direct_identifier_overlap,
    )


def foreign_key_integrity(
    generated: dict[str, pd.DataFrame],
    tables: Iterable[TableContext],
) -> tuple[float, list[Metric]]:
    checks: list[bool] = []
    metrics: list[Metric] = []
    for table in tables:
        child = generated[table.name]
        for fk in table.foreign_keys:
            parent_values = set(
                generated[fk.references_table][fk.references_column].dropna().astype(str)
            )
            child_values = set(child[fk.column].dropna().astype(str))
            missing = child_values - parent_values
            valid = len(missing) == 0
            checks.append(valid)
            metrics.append(
                Metric(
                    name=f"fk:{table.name}.{fk.column}",
                    value=len(missing),
                    status="pass" if valid else "fail",
                    detail=f"Orphan keys against {fk.references_table}.{fk.references_column}.",
                )
            )
    score = 100.0 * (sum(checks) / max(len(checks), 1)) if checks else 100.0
    return round(score, 1), metrics


def evaluate_cardinality(
    source_parent: pd.DataFrame,
    source_child: pd.DataFrame,
    synthetic_parent: pd.DataFrame,
    synthetic_child: pd.DataFrame,
    fk: Any,
) -> Metric:
    """Compare the shape of the children-per-parent distribution.

    Counts are normalized by the mean count so the metric is not penalized by
    the overall scale factor: a scale=0.5 twin should still reproduce the same
    one-to-many shape as the source.
    """
    source_counts = source_child.groupby(fk.column).size()
    synthetic_counts = synthetic_child.groupby(fk.column).size()

    source_index = source_parent[fk.references_column].astype(str).unique()
    synthetic_index = synthetic_parent[fk.references_column].astype(str).unique()

    source_full = source_counts.reindex(source_index, fill_value=0)
    synthetic_full = synthetic_counts.reindex(synthetic_index, fill_value=0)

    source_mean = max(source_full.mean(), 1e-9)
    synthetic_mean = max(synthetic_full.mean(), 1e-9)

    source_norm = (source_full / source_mean).round(2)
    synthetic_norm = (synthetic_full / synthetic_mean).round(2)

    source_dist = source_norm.value_counts(normalize=True).sort_index()
    synthetic_dist = synthetic_norm.value_counts(normalize=True).sort_index()

    categories = source_dist.index.union(synthetic_dist.index)
    tvd = 0.5 * float(
        (
            source_dist.reindex(categories, fill_value=0)
            - synthetic_dist.reindex(categories, fill_value=0)
        )
        .abs()
        .sum()
    )
    score = 1.0 - tvd
    return Metric(
        name=f"cardinality:{fk.references_table}_to_{fk.column}",
        value=round(score, 4),
        status=_status(score, CARDINALITY_GOOD, CARDINALITY_WARN),
        detail="Shape similarity of children-per-parent after mean-normalization.",
    )


def evaluate_relationships(
    source_frames: dict[str, pd.DataFrame],
    synthetic_frames: dict[str, pd.DataFrame],
    tables: list[TableContext],
) -> list[Metric]:
    metrics: list[Metric] = []

    # Diagnosis (patients) -> procedure (encounters) co-occurrence.
    if "patients" in source_frames and "encounters" in source_frames:
        source_joined = source_frames["patients"].merge(
            source_frames["encounters"], on="patient_id", how="inner", suffixes=("", "_enc")
        )
        synthetic_joined = synthetic_frames["patients"].merge(
            synthetic_frames["encounters"], on="patient_id", how="inner", suffixes=("", "_enc")
        )
        if {"diagnosis_code", "procedure_code"}.issubset(source_joined.columns):
            score = _joint_categorical_similarity(
                source_joined["diagnosis_code"],
                source_joined["procedure_code"],
                synthetic_joined["diagnosis_code"],
                synthetic_joined["procedure_code"],
            )
            metrics.append(
                Metric(
                    name="relationship:diagnosis_to_procedure",
                    value=round(score, 4),
                    status=_status(score, RELATIONSHIP_GOOD, RELATIONSHIP_WARN),
                    detail="One minus TVD of the diagnosis/procedure joint distribution.",
                )
            )

    # Age group -> diagnosis relationship.
    if "patients" in source_frames and "patients" in synthetic_frames:
        source_age_diag = _age_group_diagnosis_frame(source_frames["patients"])
        synthetic_age_diag = _age_group_diagnosis_frame(synthetic_frames["patients"])
        if source_age_diag is not None and synthetic_age_diag is not None:
            score = _categorical_similarity(
                source_age_diag["age_group_diagnosis"], synthetic_age_diag["age_group_diagnosis"]
            )
            metrics.append(
                Metric(
                    name="relationship:age_group_to_diagnosis",
                    value=round(score, 4),
                    status=_status(score, RELATIONSHIP_GOOD, RELATIONSHIP_WARN),
                    detail="One minus TVD of the age-group/diagnosis joint distribution.",
                )
            )

    return metrics


def _age_group_diagnosis_frame(frame: pd.DataFrame) -> pd.DataFrame | None:
    if "date_of_birth" not in frame.columns or "diagnosis_code" not in frame.columns:
        return None
    parsed = pd.to_datetime(frame["date_of_birth"], errors="coerce")
    if parsed.dropna().empty:
        return None
    now = pd.Timestamp.now()
    age = (now - parsed).dt.days // 365
    age_group = (age // 10 * 10).astype("Int64").astype(str) + "s"
    out = frame[["diagnosis_code"]].copy()
    out["age_group_diagnosis"] = age_group + "|" + frame["diagnosis_code"].astype(str)
    return out


def _joint_categorical_similarity(
    left_a: pd.Series, left_b: pd.Series, right_a: pd.Series, right_b: pd.Series
) -> float:
    left = (left_a.astype(str) + "|" + left_b.astype(str)).value_counts(normalize=True)
    right = (right_a.astype(str) + "|" + right_b.astype(str)).value_counts(normalize=True)
    categories = left.index.union(right.index)
    tvd = 0.5 * float(
        (left.reindex(categories, fill_value=0) - right.reindex(categories, fill_value=0))
        .abs()
        .sum()
    )
    return 1.0 - tvd


def evaluate_aggregate_queries(
    source_frames: dict[str, pd.DataFrame],
    synthetic_frames: dict[str, pd.DataFrame],
    tables: list[TableContext],
) -> list[Metric]:
    metrics: list[Metric] = []

    # Encounter volume by facility.
    if "encounters" in source_frames and "encounters" in synthetic_frames:
        score = _categorical_similarity(
            source_frames["encounters"]["facility"], synthetic_frames["encounters"]["facility"]
        )
        metrics.append(
            Metric(
                name="aggregate_query:encounters_by_facility",
                value=round(score, 4),
                status=_status(score, AGGREGATE_QUERY_GOOD, AGGREGATE_QUERY_WARN),
                detail="One minus TVD of encounter counts by facility.",
            )
        )

    # Average claim amount by procedure.
    if "encounters" in source_frames and "encounters" in synthetic_frames:
        score = _group_mean_similarity(
            source_frames["encounters"],
            synthetic_frames["encounters"],
            group_col="procedure_code",
            value_col="claim_amount",
        )
        metrics.append(
            Metric(
                name="aggregate_query:mean_claim_by_procedure",
                value=round(score, 4),
                status=_status(score, AGGREGATE_QUERY_GOOD, AGGREGATE_QUERY_WARN),
                detail="Similarity of average claim_amount per procedure_code.",
            )
        )

    # Patient volume by age group.
    if "patients" in source_frames and "patients" in synthetic_frames:
        source_age = _age_group_series(source_frames["patients"])
        synthetic_age = _age_group_series(synthetic_frames["patients"])
        if source_age is not None and synthetic_age is not None:
            score = _categorical_similarity(source_age, synthetic_age)
            metrics.append(
                Metric(
                    name="aggregate_query:patients_by_age_group",
                    value=round(score, 4),
                    status=_status(score, AGGREGATE_QUERY_GOOD, AGGREGATE_QUERY_WARN),
                    detail="One minus TVD of patient counts by age group.",
                )
            )

    return metrics


def _age_group_series(frame: pd.DataFrame) -> pd.Series | None:
    if "date_of_birth" not in frame.columns:
        return None
    parsed = pd.to_datetime(frame["date_of_birth"], errors="coerce")
    if parsed.dropna().empty:
        return None
    now = pd.Timestamp.now()
    age = (now - parsed).dt.days // 365
    return (age // 10 * 10).astype("Int64").astype(str) + "s"


def _group_mean_similarity(
    source: pd.DataFrame, synthetic: pd.DataFrame, group_col: str, value_col: str
) -> float:
    source_means = (
        pd.to_numeric(source[value_col], errors="coerce").groupby(source[group_col]).mean()
    )
    synthetic_means = (
        pd.to_numeric(synthetic[value_col], errors="coerce").groupby(synthetic[group_col]).mean()
    )
    groups = source_means.index.union(synthetic_means.index)
    left = source_means.reindex(groups)
    right = synthetic_means.reindex(groups)
    scale = max(float(left.abs().mean()), 1e-9)
    error = float((left - right).abs().mean())
    return 1.0 - min(error / scale, 1.0)


def evaluate_integrity(
    source_frames: dict[str, pd.DataFrame],
    synthetic_frames: dict[str, pd.DataFrame],
    tables: list[TableContext],
) -> tuple[float, float, list[Metric]]:
    fk_score, fk_metrics = foreign_key_integrity(synthetic_frames, tables)
    metrics = list(fk_metrics)

    cardinality_scores: list[float] = []
    table_by_name = {table.name: table for table in tables}
    for table in tables:
        for fk in table.foreign_keys:
            parent_table = table_by_name.get(fk.references_table)
            if parent_table is None:
                continue
            metric = evaluate_cardinality(
                source_frames[fk.references_table],
                source_frames[table.name],
                synthetic_frames[fk.references_table],
                synthetic_frames[table.name],
                fk,
            )
            metrics.append(metric)
            cardinality_scores.append(float(metric.value))

    scores = [fk_score]
    if cardinality_scores:
        scores.append(100.0 * (sum(cardinality_scores) / len(cardinality_scores)))
    integrity_score = round(sum(scores) / len(scores), 1)
    return integrity_score, fk_score, metrics


def summarize_privacy(reports: list[TableReport]) -> dict[str, Any]:
    exact_overlap = 0
    direct_overlap = 0
    singling_out_values: list[float] = []
    failed_gates: list[str] = []

    for report in reports:
        for metric in report.privacy_metrics:
            if metric.name == "exact_row_overlap":
                exact_overlap += int(metric.value)
            elif metric.name == "direct_identifier_overlap":
                direct_overlap += int(metric.value)
            elif metric.name == "quasi_identifier_singling_out_rate":
                singling_out_values.append(float(metric.value))
            if metric.status == "fail":
                failed_gates.append(f"{report.table}.{metric.name}")

    return {
        "exact_row_overlap": exact_overlap,
        "direct_identifier_overlap": direct_overlap,
        "singling_out_rate": round(max(singling_out_values) if singling_out_values else 0.0, 4),
        "failed_gates": failed_gates,
    }


def summarize_utility(reports: list[TableReport]) -> dict[str, Any]:
    distribution_scores: list[float] = []
    failed_gates: list[str] = []
    metric_names: list[str] = []

    for report in reports:
        for metric in report.utility_metrics:
            if (
                metric.name.startswith("distribution:")
                or metric.name.startswith("date_distribution:")
                or metric.name == "correlation_similarity"
                or metric.name.startswith("conditional_mean:")
                or metric.name.startswith("cardinality:")
                or metric.name.startswith("relationship:")
                or metric.name.startswith("aggregate_query:")
            ):
                distribution_scores.append(float(metric.value))
                metric_names.append(metric.name)
            if metric.status == "fail":
                failed_gates.append(f"{report.table}.{metric.name}")

    return {
        "distribution_scores": distribution_scores,
        "metric_names": metric_names,
        "mean_distribution_similarity": round(
            sum(distribution_scores) / max(len(distribution_scores), 1), 4
        ),
        "failed_gates": failed_gates,
    }


def summarize_integrity(integrity_score: float, metrics: list[Metric]) -> dict[str, Any]:
    failed_gates = [metric.name for metric in metrics if metric.status == "fail"]
    orphan_count = sum(int(metric.value) for metric in metrics if metric.name.startswith("fk:"))
    return {
        "integrity_score": integrity_score,
        "orphan_foreign_keys": orphan_count,
        "failed_gates": failed_gates,
    }


def render_decision(
    privacy_score: float,
    utility_score: float,
    integrity_score: float,
    exact_overlap: int,
    direct_identifier_overlap: int,
    privacy_summary: dict[str, Any],
    utility_summary: dict[str, Any],
    integrity_summary: dict[str, Any],
) -> tuple[str, list[str]]:
    decision = "VERIFIED"
    reasons: list[str] = []

    if privacy_score < PRIVACY_SCORE_THRESHOLD:
        decision = "REJECTED"
        reasons.append(
            f"Privacy score {privacy_score} is below the required {PRIVACY_SCORE_THRESHOLD}."
        )
    if direct_identifier_overlap > 0:
        decision = "REJECTED"
        reasons.append(
            f"{direct_identifier_overlap} direct-identifier value(s) overlap with the source."
        )
    if exact_overlap > 0:
        decision = "REJECTED"
        reasons.append(f"{exact_overlap} complete source row(s) were reproduced.")
    if privacy_summary.get("failed_gates"):
        decision = "REJECTED"
        for gate in privacy_summary["failed_gates"]:
            reasons.append(f"Privacy gate failed: {gate}.")

    if integrity_score < INTEGRITY_SCORE_THRESHOLD:
        decision = "REJECTED"
        reasons.append(
            f"Integrity score {integrity_score} is below the required {INTEGRITY_SCORE_THRESHOLD}."
        )
    if integrity_summary.get("failed_gates"):
        decision = "REJECTED"
        for gate in integrity_summary["failed_gates"]:
            reasons.append(f"Integrity gate failed: {gate}.")

    if utility_score < UTILITY_SCORE_THRESHOLD:
        decision = "REJECTED"
        reasons.append(
            f"Utility score {utility_score} is below the required {UTILITY_SCORE_THRESHOLD}."
        )
    if utility_summary.get("failed_gates"):
        decision = "REJECTED"
        for gate in utility_summary["failed_gates"]:
            reasons.append(f"Utility gate failed: {gate}.")

    if decision == "VERIFIED":
        reasons.append(
            f"All privacy/integrity gates passed and utility score {utility_score} "
            f"cleared threshold {UTILITY_SCORE_THRESHOLD}."
        )

    return decision, reasons
