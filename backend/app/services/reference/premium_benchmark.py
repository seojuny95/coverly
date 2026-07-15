"""Age-band premium burden guide lookup from the configured Postgres database."""

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
        return _fallback_benchmark_for_age(age)

    def list_all(self) -> tuple[PremiumBenchmark, ...]:
        return _FALLBACK_BENCHMARKS


_preloaded_benchmarks: tuple[PremiumBenchmark, ...] | None = None


def premium_benchmark_for_age(age: int | None) -> PremiumBenchmark | None:
    """Return a benchmark if reference DB is configured and reachable."""

    if age is None:
        return None

    if _preloaded_benchmarks is not None:
        return _find_preloaded_benchmark(age)

    try:
        benchmark = _cached_premium_benchmark_for_age(age)
    except Exception:
        return _fallback_benchmark_for_age(age)
    return benchmark or _fallback_benchmark_for_age(age)


def warm_premium_benchmark_cache() -> int:
    """Preload reference benchmarks without making app startup depend on DB."""

    global _preloaded_benchmarks

    try:
        benchmarks = _repository().list_all()
    except Exception:
        benchmarks = _FALLBACK_BENCHMARKS

    if not benchmarks:
        benchmarks = _FALLBACK_BENCHMARKS

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
        return _fallback_benchmark_for_age(age)
    for benchmark in _preloaded_benchmarks:
        if benchmark.min_age <= age <= benchmark.max_age:
            return benchmark
    return _fallback_benchmark_for_age(age)


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
        reliability=str(row[f"{prefix}_reliability"]),
        caveat=str(row[f"{prefix}_caveat"]),
    )


_KOSIS_SOURCE = PremiumBenchmarkSource(
    label="KOSIS 국가통계포털 · 성별 연령대별 소득",
    url=(
        "https://kosis.kr/statHtml/statHtml.do?sso=ok&returnurl="
        "https%3A%2F%2Fkosis.kr%3A443%2FstatHtml%2FstatHtml.do%3F"
        "conn_path%3DI2%26tblId%3DDT_1EP_2010%26orgId%3D101%26"
    ),
    published_at="2025-01-01",
    reliability="official",
    caveat="연령대 평균 소득은 개인 소득과 다를 수 있어요.",
)
_INCOME_GUIDE_SOURCE = PremiumBenchmarkSource(
    label="뱅크샐러드 · 나에게 맞는 보험료 계산법",
    url=(
        "https://www.banksalad.com/articles/"
        "%EB%B3%B4%ED%97%98-%EB%B3%B4%ED%97%98%EB%A6%AC%EB%AA%A8%EB%8D%B8%EB%A7%81-"
        "%EB%B3%B4%ED%97%98%EB%A3%8C"
    ),
    published_at="2025-01-01",
    reliability="private_guidance",
    caveat="월 소득의 5%~10% 범위는 민간 가이드예요. 적정 보험료의 공식 기준은 아니에요.",
)


def _fallback_benchmark(
    *,
    age_band_label: str,
    min_age: int,
    max_age: int,
    average_monthly_income: int,
) -> PremiumBenchmark:
    return PremiumBenchmark(
        age_band_label=age_band_label,
        min_age=min_age,
        max_age=max_age,
        average_monthly_income=average_monthly_income,
        suggested_min_ratio=0.05,
        suggested_max_ratio=0.10,
        suggested_min_premium=round(average_monthly_income * 0.05),
        suggested_max_premium=round(average_monthly_income * 0.10),
        income_source=_KOSIS_SOURCE,
        guide_source=_INCOME_GUIDE_SOURCE,
    )


_FALLBACK_BENCHMARKS = (
    _fallback_benchmark(
        age_band_label="20~29세",
        min_age=20,
        max_age=29,
        average_monthly_income=2_630_000,
    ),
    _fallback_benchmark(
        age_band_label="30~39세",
        min_age=30,
        max_age=39,
        average_monthly_income=3_860_000,
    ),
    _fallback_benchmark(
        age_band_label="40~49세",
        min_age=40,
        max_age=49,
        average_monthly_income=4_510_000,
    ),
    _fallback_benchmark(
        age_band_label="50~59세",
        min_age=50,
        max_age=59,
        average_monthly_income=4_290_000,
    ),
    _fallback_benchmark(
        age_band_label="60세 이상",
        min_age=60,
        max_age=120,
        average_monthly_income=2_500_000,
    ),
)


def _fallback_benchmark_for_age(age: int | None) -> PremiumBenchmark | None:
    if age is None:
        return None
    for benchmark in _FALLBACK_BENCHMARKS:
        if benchmark.min_age <= age <= benchmark.max_age:
            return benchmark
    return None
