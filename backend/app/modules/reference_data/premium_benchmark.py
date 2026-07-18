"""Age-band premium burden guide lookup from the configured Postgres database."""

import logging
from functools import lru_cache
from typing import Protocol

from app.core.config import get_settings
from app.integrations.postgres.premium_benchmark_store import (
    PostgresPremiumBenchmarkRepository,
)
from app.modules.reference_data.contracts import PremiumBenchmark

logger = logging.getLogger(__name__)


class PremiumBenchmarkRepository(Protocol):
    def find_by_age(self, age: int | None) -> PremiumBenchmark | None: ...

    def list_all(self) -> tuple[PremiumBenchmark, ...]: ...


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
        # An empty tuple is a successful result. Do not cache it after a
        # transient failure, or later requests could never retry the database.
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
