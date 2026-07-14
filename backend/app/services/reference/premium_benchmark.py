"""Age-band premium benchmark lookup from the configured Postgres database."""

from functools import lru_cache
from typing import Any, Protocol

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from app.schemas.analysis import PremiumBenchmark, PremiumBenchmarkSource
from app.settings import get_settings


class PremiumBenchmarkRepository(Protocol):
    def find_by_age(self, age: int | None) -> PremiumBenchmark | None: ...

    def list_all(self) -> tuple[PremiumBenchmark, ...]: ...


class PostgresPremiumBenchmarkRepository:
    """Read reference premiums from Supabase/Postgres.

    Expected tables:
    - reference.sources(id, title, publisher, url, published_at, reliability, caveat)
    - reference.premium_benchmarks(source_id, age_band_label, min_age, max_age,
      average_monthly_premium, effective_at)
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
            WHERE %s BETWEEN b.min_age AND b.max_age
            ORDER BY b.effective_at DESC, b.max_age ASC
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
            ORDER BY b.effective_at DESC, b.min_age ASC, b.max_age ASC
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
        return None


def warm_premium_benchmark_cache() -> int:
    """Preload reference benchmarks without making app startup depend on DB."""

    global _preloaded_benchmarks

    try:
        benchmarks = _repository().list_all()
    except Exception:
        return 0

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
        benchmark_table=settings.premium_benchmark_table,
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
          b.age_band_label,
          b.min_age,
          b.max_age,
          b.average_monthly_premium,
          s.title AS source_title,
          s.publisher AS source_publisher,
          s.url AS source_url,
          s.published_at AS source_published_at,
          s.reliability AS source_reliability,
          s.caveat AS source_caveat
        FROM {benchmark_table} b
        JOIN {source_table} s ON s.id = b.source_id
        """
        + suffix
    ).format(
        benchmark_table=sql.Identifier(schema, benchmark_table),
        source_table=sql.Identifier(schema, source_table),
    )


def _benchmark_from_row(row: dict[str, Any]) -> PremiumBenchmark:
    publisher = str(row["source_publisher"] or "").strip()
    source_title = str(row["source_title"])
    label = f"{publisher} · {source_title}" if publisher else source_title

    return PremiumBenchmark(
        age_band_label=str(row["age_band_label"]),
        min_age=int(row["min_age"]),
        max_age=int(row["max_age"]),
        average_monthly_premium=int(row["average_monthly_premium"]),
        source=PremiumBenchmarkSource(
            label=label,
            url=str(row["source_url"]),
            published_at=str(row["source_published_at"]),
            reliability=str(row["source_reliability"]),
            caveat=str(row["source_caveat"]),
        ),
    )
