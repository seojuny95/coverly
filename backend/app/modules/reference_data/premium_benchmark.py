"""Age-band premium burden guide lookup from the configured Postgres database."""

import logging
from functools import lru_cache
from typing import Any, Protocol

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from app.core.config import get_settings
from app.modules.portfolio.schemas import (
    PremiumBenchmark,
    PremiumBenchmarkSource,
    SourceReliability,
)

logger = logging.getLogger(__name__)


class PremiumBenchmarkRepository(Protocol):
    def find_by_age(self, age: int | None) -> PremiumBenchmark | None: ...

    def list_all(self) -> tuple[PremiumBenchmark, ...]: ...


class PostgresPremiumBenchmarkRepository:
    """Read reference premium guides from Supabase/Postgres.

    Expected tables:
    - reference.sources(id, title, publisher, url, published_at, reliability, caveat)
    - reference.premium_burden_guides(
        income_source_id,
        guide_source_id,
        age_band_label,
        min_age,
        max_age,
        average_monthly_income,
        suggested_min_ratio,
        suggested_max_ratio,
        effective_at
      )
    """

    def __init__(
        self,
        database_url: str,
        *,
        schema: str,
        benchmark_table: str,
        source_table: str,
    ) -> None:
        self._database_url = database_url
        self._schema = schema
        self._benchmark_table = benchmark_table
        self._source_table = source_table

    def find_by_age(self, age: int | None) -> PremiumBenchmark | None:
        if age is None:
            return None

        query = _benchmark_query(
            """
            WHERE %s BETWEEN g.min_age AND g.max_age
            ORDER BY g.effective_at DESC, g.max_age ASC
            LIMIT 1
            """,
            schema=self._schema,
            benchmark_table=self._benchmark_table,
            source_table=self._source_table,
        )
        with psycopg.connect(self._database_url, row_factory=dict_row) as connection:
            row = connection.execute(query, (age,)).fetchone()
        if row is None:
            return None
        return _benchmark_from_row(row)

    def list_all(self) -> tuple[PremiumBenchmark, ...]:
        query = _benchmark_query(
            """
            ORDER BY g.effective_at DESC, g.min_age ASC, g.max_age ASC
            """,
            schema=self._schema,
            benchmark_table=self._benchmark_table,
            source_table=self._source_table,
        )
        with psycopg.connect(self._database_url, row_factory=dict_row) as connection:
            rows = connection.execute(query).fetchall()
        return tuple(_benchmark_from_row(row) for row in rows)


class NullPremiumBenchmarkRepository:
    def find_by_age(self, age: int | None) -> PremiumBenchmark | None:
        return None

    def list_all(self) -> tuple[PremiumBenchmark, ...]:
        return ()


_preloaded_benchmarks: tuple[PremiumBenchmark, ...] | None = None


def premium_benchmark_for_age(age: int | None) -> PremiumBenchmark | None:
    """Return a benchmark if reference DB is configured and reachable."""

    if age is None:
        return None

    if _preloaded_benchmarks is not None:
        return _find_preloaded_benchmark(age)

    try:
        return _cached_premium_benchmark_for_age(age)
    except Exception:
        logger.exception("premium_benchmark_lookup_failed")
        return None


def warm_premium_benchmark_cache() -> int:
    """Preload reference benchmarks without making app startup depend on DB."""

    global _preloaded_benchmarks

    try:
        benchmarks = _repository().list_all()
    except Exception:
        logger.exception("premium_benchmark_cache_warm_failed")
        benchmarks = ()

    _preloaded_benchmarks = benchmarks
    return len(benchmarks)


@lru_cache(maxsize=128)
def _cached_premium_benchmark_for_age(age: int) -> PremiumBenchmark | None:
    return _repository().find_by_age(age)


@lru_cache(maxsize=1)
def _repository() -> PremiumBenchmarkRepository:
    settings = get_settings()
    if not settings.database_url:
        return NullPremiumBenchmarkRepository()
    return PostgresPremiumBenchmarkRepository(
        settings.database_url,
        schema=settings.reference_schema,
        benchmark_table=settings.premium_burden_guide_table,
        source_table=settings.reference_source_table,
    )


def _find_preloaded_benchmark(age: int) -> PremiumBenchmark | None:
    if _preloaded_benchmarks is None:
        return None
    for benchmark in _preloaded_benchmarks:
        if benchmark.min_age <= age <= benchmark.max_age:
            return benchmark
    return None


def _benchmark_query(
    suffix: str,
    *,
    schema: str,
    benchmark_table: str,
    source_table: str,
) -> sql.Composed:
    return sql.SQL(
        """
        SELECT
          g.age_band_label,
          g.min_age,
          g.max_age,
          g.average_monthly_income,
          g.suggested_min_ratio,
          g.suggested_max_ratio,
          income.title AS income_source_title,
          income.publisher AS income_source_publisher,
          income.url AS income_source_url,
          income.published_at AS income_source_published_at,
          income.reliability AS income_source_reliability,
          income.caveat AS income_source_caveat,
          guide.title AS guide_source_title,
          guide.publisher AS guide_source_publisher,
          guide.url AS guide_source_url,
          guide.published_at AS guide_source_published_at,
          guide.reliability AS guide_source_reliability,
          guide.caveat AS guide_source_caveat
        FROM {benchmark_table} g
        JOIN {source_table} income ON income.id = g.income_source_id
        JOIN {source_table} guide ON guide.id = g.guide_source_id
        """
        + suffix
    ).format(
        benchmark_table=sql.Identifier(schema, benchmark_table),
        source_table=sql.Identifier(schema, source_table),
    )


def _benchmark_from_row(row: dict[str, Any]) -> PremiumBenchmark:
    average_monthly_income = int(row["average_monthly_income"])
    suggested_min_ratio = float(row["suggested_min_ratio"])
    suggested_max_ratio = float(row["suggested_max_ratio"])

    return PremiumBenchmark(
        age_band_label=str(row["age_band_label"]),
        min_age=int(row["min_age"]),
        max_age=int(row["max_age"]),
        average_monthly_income=average_monthly_income,
        suggested_min_ratio=suggested_min_ratio,
        suggested_max_ratio=suggested_max_ratio,
        suggested_min_premium=int(round(average_monthly_income * suggested_min_ratio)),
        suggested_max_premium=int(round(average_monthly_income * suggested_max_ratio)),
        income_source=_source_from_row(row, prefix="income_source"),
        guide_source=_source_from_row(row, prefix="guide_source"),
    )


def _source_from_row(row: dict[str, Any], *, prefix: str) -> PremiumBenchmarkSource:
    publisher = str(row[f"{prefix}_publisher"] or "").strip()
    title = str(row[f"{prefix}_title"])
    label = f"{publisher} · {title}" if publisher else title
    return PremiumBenchmarkSource(
        label=label,
        url=str(row[f"{prefix}_url"]),
        published_at=str(row[f"{prefix}_published_at"]),
        reliability=_source_reliability(row[f"{prefix}_reliability"]),
        caveat=str(row[f"{prefix}_caveat"]),
    )


def _source_reliability(value: object) -> SourceReliability:
    allowed: set[SourceReliability] = {
        "official",
        "public_research",
        "industry",
        "large_private_analysis",
        "private_guidance",
    }
    if value not in allowed:
        raise ValueError("unknown premium benchmark source reliability")
    return value
