"""Age-band premium burden guide lookup from the configured Postgres database."""

import logging
from functools import lru_cache
from threading import Lock
from time import monotonic
from typing import Protocol

from app.core.config import get_settings
from app.integrations.postgres.premium_benchmark_store import (
    PostgresPremiumBenchmarkRepository,
)
from app.modules.reference_data.contracts import PremiumBenchmark

logger = logging.getLogger(__name__)

_FAILURE_BACKOFF_SECONDS = 5.0


class PremiumBenchmarkRepository(Protocol):
    def find_by_age(self, age: int | None) -> PremiumBenchmark | None: ...

    def list_all(self) -> tuple[PremiumBenchmark, ...]: ...


class NullPremiumBenchmarkRepository:
    def find_by_age(self, age: int | None) -> PremiumBenchmark | None:
        return None

    def list_all(self) -> tuple[PremiumBenchmark, ...]:
        return ()


_preloaded_benchmarks: tuple[PremiumBenchmark, ...] | None = None
_failure_retry_at: float | None = None
_lookup_lock = Lock()


def premium_benchmark_for_age(age: int | None) -> PremiumBenchmark | None:
    """Return a benchmark if reference DB is configured and reachable."""

    global _failure_retry_at

    if age is None:
        return None

    if _preloaded_benchmarks is not None:
        return _find_preloaded_benchmark(age)

    if _retry_is_deferred():
        return None

    with _lookup_lock:
        if _preloaded_benchmarks is not None:
            return _find_preloaded_benchmark(age)
        if _retry_is_deferred():
            return None

        if _failure_retry_at is not None:
            # A cached value cannot prove that the database recovered.
            _cached_premium_benchmark_for_age.cache_clear()
        try:
            benchmark = _cached_premium_benchmark_for_age(age)
        except Exception:
            _defer_retry()
            logger.exception("premium_benchmark_lookup_failed")
            return None

        _failure_retry_at = None
        return benchmark


def warm_premium_benchmark_cache() -> int:
    """Preload reference benchmarks without making app startup depend on DB."""

    global _failure_retry_at, _preloaded_benchmarks

    with _lookup_lock:
        try:
            benchmarks = _repository().list_all()
        except Exception:
            _defer_retry()
            logger.exception("premium_benchmark_cache_warm_failed")
            # An empty tuple is a successful result. Do not cache it after a
            # transient failure, or later requests could never retry the database.
            return 0

        _preloaded_benchmarks = benchmarks
        _failure_retry_at = None
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


def _retry_is_deferred() -> bool:
    return _failure_retry_at is not None and monotonic() < _failure_retry_at


def _defer_retry() -> None:
    global _failure_retry_at

    _failure_retry_at = monotonic() + _FAILURE_BACKOFF_SECONDS
