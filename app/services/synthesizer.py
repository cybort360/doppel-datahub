from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
import pandas as pd
from faker import Faker
from scipy.stats import norm

from app.models import ColumnContext, DatasetContext, SemanticType, TableContext


@dataclass
class GeneratedTable:
    source: pd.DataFrame
    synthetic: pd.DataFrame
    table: TableContext


class SyntheticGenerator:
    """Metadata-driven synthesizer with deterministic IDs and FK-safe multi-table output.

    This is deliberately transparent rather than a black-box model. Numerical columns use
    empirical quantiles (and a Gaussian copula when several numeric columns exist), while
    categorical and date columns preserve observed distributions without copying full rows.
    """

    def __init__(self, seed: int) -> None:
        self.seed = seed
        self.rng = np.random.default_rng(seed)
        self.fake = Faker()
        self.fake.seed_instance(seed)
        self.id_maps: dict[tuple[str, str], dict[str, str]] = {}

    def generate_dataset(
        self,
        context: DatasetContext,
        frames: dict[str, pd.DataFrame],
        scale: float,
    ) -> dict[str, GeneratedTable]:
        output: dict[str, GeneratedTable] = {}
        pending = {table.name: table for table in context.tables}

        while pending:
            progressed = False
            for table_name, table in list(pending.items()):
                if all(fk.references_table in output for fk in table.foreign_keys):
                    source = frames[table_name]
                    count = max(1, int(round(len(source) * scale)))
                    synthetic = self._generate_table(table, source, count)
                    output[table_name] = GeneratedTable(source, synthetic, table)
                    del pending[table_name]
                    progressed = True
            if not progressed:
                unresolved = ", ".join(pending)
                raise ValueError(f"Circular or missing foreign-key dependency: {unresolved}")

        return output

    def _generate_table(
        self, table: TableContext, source: pd.DataFrame, count: int
    ) -> pd.DataFrame:
        generated = pd.DataFrame(index=range(count))
        columns = {column.name: column for column in table.columns}

        conditional_numeric = {
            name: column.strategy.split(":", 1)[1]
            for name, column in columns.items()
            if column.semantic_type == SemanticType.NUMERIC
            and column.strategy.startswith("conditional_on:")
        }
        numeric_columns = [
            name
            for name, column in columns.items()
            if column.semantic_type == SemanticType.NUMERIC
            and name not in conditional_numeric
        ]
        numeric_samples = self._sample_numeric_block(source, numeric_columns, count)

        # Generate identifiers and categorical context before conditioned numeric fields.
        for name in source.columns:
            if name in conditional_numeric:
                continue
            column = columns[name]
            if name in numeric_samples:
                values = numeric_samples[name]
            else:
                values = self._generate_column(table, column, source[name], count)
            generated[name] = values

        for name, condition_column in conditional_numeric.items():
            if condition_column not in generated:
                raise ValueError(
                    f"Conditioning column {condition_column} must be generated before {name}"
                )
            generated[name] = self._sample_conditional_numeric(
                source=source,
                value_column=name,
                condition_column=condition_column,
                generated_conditions=generated[condition_column],
                count=count,
            )

        return generated[source.columns]

    def _generate_column(
        self,
        table: TableContext,
        column: ColumnContext,
        source: pd.Series,
        count: int,
    ) -> Iterable[object]:
        semantic = column.semantic_type
        null_mask = self.rng.random(count) < float(source.isna().mean())

        if semantic == SemanticType.IDENTIFIER:
            prefix = re.sub(r"[^A-Z0-9]", "", table.name.upper())[:4] or "ROW"
            values = [f"SYN-{prefix}-{self.seed:04d}-{i + 1:07d}" for i in range(count)]
            self._build_id_map(table, column, source, values)
            return values
        if semantic == SemanticType.FOREIGN_KEY:
            return self._generate_foreign_keys(table, column, source, count)
        if semantic == SemanticType.EMAIL:
            values = [
                f"synthetic.{self.fake.unique.user_name()}.{i}@example.test"
                for i in range(count)
            ]
        elif semantic == SemanticType.PERSON_NAME:
            first = "first" in column.name.lower()
            last = "last" in column.name.lower()
            values = [
                (
                    f"{self.fake.first_name()}-SYN-{i + 1:05d}"
                    if first
                    else f"{self.fake.last_name()}-SYN-{i + 1:05d}"
                    if last
                    else f"{self.fake.name()}-SYN-{i + 1:05d}"
                )
                for i in range(count)
            ]
        elif semantic == SemanticType.DATE_OF_BIRTH:
            values = self._sample_dates(source, count, jitter_days=45, clamp_future=True)
        elif semantic == SemanticType.DATETIME:
            values = self._sample_dates(source, count, jitter_days=14, clamp_future=False)
        elif semantic == SemanticType.POSTAL_CODE:
            values = [f"TST-{self.fake.postcode()}-{i + 1:05d}" for i in range(count)]
        elif semantic == SemanticType.CATEGORICAL:
            values = self._sample_categorical(source, count)
        elif semantic == SemanticType.BOOLEAN:
            probability = float(pd.to_numeric(source, errors="coerce").mean())
            values = self.rng.random(count) < probability
        else:
            values = [self.fake.sentence(nb_words=6) for _ in range(count)]

        output = np.asarray(values, dtype=object)
        if null_mask.any() and semantic not in {SemanticType.IDENTIFIER, SemanticType.FOREIGN_KEY}:
            output[null_mask] = None
        return output

    def _build_id_map(
        self,
        table: TableContext,
        column: ColumnContext,
        source: pd.Series,
        generated_values: list[str],
    ) -> None:
        unique_source = [str(value) for value in source.dropna().astype(str).unique()]
        if not generated_values:
            raise ValueError(f"No generated identifiers for {table.name}.{column.name}")
        # Preserve cardinality when possible: assign each source key a distinct
        # synthetic key. Only allow collisions when the synthetic table is smaller
        # than the set of source keys (scale < 1).
        replace = len(generated_values) < len(unique_source)
        assignments = self.rng.choice(
            generated_values, size=len(unique_source), replace=replace
        ).tolist()
        self.id_maps[(table.name, column.name)] = dict(
            zip(unique_source, assignments, strict=True)
        )

    def _generate_foreign_keys(
        self,
        table: TableContext,
        column: ColumnContext,
        source: pd.Series,
        count: int,
    ) -> list[str | None]:
        fk = next((item for item in table.foreign_keys if item.column == column.name), None)
        if fk is None:
            raise ValueError(f"Missing foreign-key metadata for {table.name}.{column.name}")
        mapping = self.id_maps.get((fk.references_table, fk.references_column))
        if not mapping:
            raise ValueError(
                f"Parent key map not generated for {fk.references_table}.{fk.references_column}"
            )

        # Build a weighted pool of synthetic parent IDs that mirrors the source
        # cardinality distribution. Sampling without replacement when possible
        # preserves the exact one-to-many shape at scale=1.
        source_counts = source.astype("string").value_counts(dropna=True)
        synthetic_pool: list[str] = []
        for source_value, occurrences in source_counts.items():
            synthetic_value = mapping.get(str(source_value))
            if synthetic_value is not None:
                synthetic_pool.extend([synthetic_value] * int(occurrences))

        if not synthetic_pool:
            raise ValueError(f"Empty foreign-key pool for {table.name}.{column.name}")

        replace = count > len(synthetic_pool)
        sampled = self.rng.choice(synthetic_pool, size=count, replace=replace).tolist()
        return sampled

    def _sample_categorical(self, source: pd.Series, count: int) -> np.ndarray:
        clean = source.dropna().astype(str)
        if clean.empty:
            return np.array([None] * count, dtype=object)
        probabilities = clean.value_counts(normalize=True)
        return self.rng.choice(
            probabilities.index.to_numpy(), size=count, p=probabilities.to_numpy()
        )

    def _sample_dates(
        self,
        source: pd.Series,
        count: int,
        jitter_days: int,
        clamp_future: bool,
    ) -> list[str | None]:
        parsed = pd.to_datetime(source, errors="coerce").dropna()
        if parsed.empty:
            return [None] * count
        timestamps = parsed.astype("int64").to_numpy()
        chosen = self.rng.choice(timestamps, size=count, replace=True)
        jitter = self.rng.integers(-jitter_days, jitter_days + 1, size=count) * 86_400_000_000_000
        sampled = pd.to_datetime(chosen + jitter)
        if clamp_future:
            max_date = parsed.max()
            sampled = sampled.where(sampled <= max_date, max_date)
        return sampled.strftime("%Y-%m-%d").tolist()


    def _sample_conditional_numeric(
        self,
        source: pd.DataFrame,
        value_column: str,
        condition_column: str,
        generated_conditions: pd.Series,
        count: int,
    ) -> np.ndarray:
        source_values = pd.to_numeric(source[value_column], errors="coerce")
        null_rate = float(source_values.isna().mean())
        fallback = source_values.dropna().to_numpy(dtype=float)
        if fallback.size == 0:
            return np.full(count, np.nan)

        output = np.empty(count, dtype=float)
        for index, condition in enumerate(generated_conditions.astype(str)):
            mask = source[condition_column].astype(str) == condition
            pool = (
                pd.to_numeric(source.loc[mask, value_column], errors="coerce")
                .dropna()
                .to_numpy(dtype=float)
            )
            if pool.size < 3:
                pool = fallback
            quantile = float(self.rng.random())
            value = float(np.quantile(np.sort(pool), quantile))
            noise = self.rng.normal(0, max(float(np.std(pool)) * 0.015, 1e-9))
            output[index] = value + noise

        output = self._coerce_numeric_shape(output, source[value_column])
        if null_rate > 0:
            output[self.rng.random(count) < null_rate] = np.nan
        return output

    @staticmethod
    def _coerce_numeric_shape(values: np.ndarray, source: pd.Series) -> np.ndarray:
        clean = pd.to_numeric(source, errors="coerce").dropna()
        if clean.empty:
            return values
        values = np.clip(values, float(clean.min()), float(clean.max()))
        if pd.api.types.is_integer_dtype(source.dtype):
            values = np.rint(values)
        return values

    def _sample_numeric_block(
        self,
        source: pd.DataFrame,
        columns: list[str],
        count: int,
    ) -> dict[str, np.ndarray]:
        if not columns:
            return {}
        clean = source[columns].apply(pd.to_numeric, errors="coerce")
        medians = clean.median(numeric_only=True)
        filled = clean.fillna(medians)

        if len(columns) == 1:
            column = columns[0]
            values = filled[column].dropna().sort_values().to_numpy(dtype=float)
            quantiles = self.rng.random(count)
            sampled = np.quantile(values, quantiles)
            noise_scale = max(float(np.std(values)) * 0.01, 1e-9)
            generated = sampled + self.rng.normal(0, noise_scale, count)
            return {column: self._coerce_numeric_shape(generated, source[column])}

        ranks = filled.rank(method="average", pct=True).clip(1e-5, 1 - 1e-5)
        gaussian = norm.ppf(ranks)
        correlation = np.corrcoef(np.asarray(gaussian), rowvar=False)
        correlation = np.nan_to_num(correlation, nan=0.0)
        correlation += np.eye(len(columns)) * 1e-6
        draws = self.rng.multivariate_normal(np.zeros(len(columns)), correlation, size=count)
        uniforms = norm.cdf(draws)

        result: dict[str, np.ndarray] = {}
        for index, column in enumerate(columns):
            values = filled[column].dropna().sort_values().to_numpy(dtype=float)
            sampled = np.quantile(values, uniforms[:, index])
            result[column] = self._coerce_numeric_shape(sampled, source[column])
        return result
