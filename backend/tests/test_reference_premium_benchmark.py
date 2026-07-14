from pytest import MonkeyPatch

from app.schemas.analysis import PremiumBenchmark, PremiumBenchmarkSource
from app.services.reference import premium_benchmark as subject


class _CountingRepository:
    def __init__(self, benchmark: PremiumBenchmark) -> None:
        self.calls = 0
        self.benchmark = benchmark

    def find_by_age(self, age: int | None) -> PremiumBenchmark | None:
        self.calls += 1
        return self.benchmark if age == 35 else None

    def list_all(self) -> tuple[PremiumBenchmark, ...]:
        self.calls += 1
        return (self.benchmark,)


def test_premium_benchmark_lookup_caches_successful_age_queries(
    monkeypatch: MonkeyPatch,
) -> None:
    benchmark = PremiumBenchmark(
        age_band_label="30대",
        min_age=30,
        max_age=39,
        average_monthly_premium=278395,
        source=PremiumBenchmarkSource(
            label="KB의 생각 · 시그널플래너 40만명 분석",
            url="https://kbthink.com/main/asset-management/insurance/insurance-2-240828.html",
            published_at="2025-06-16",
            reliability="large_private_analysis",
            caveat="평균은 적정 보험료 기준이 아니에요.",
        ),
    )
    repository = _CountingRepository(benchmark)
    monkeypatch.setattr(subject, "_repository", lambda: repository)
    subject._cached_premium_benchmark_for_age.cache_clear()
    monkeypatch.setattr(subject, "_preloaded_benchmarks", None)

    first = subject.premium_benchmark_for_age(35)
    second = subject.premium_benchmark_for_age(35)

    assert first == benchmark
    assert second == benchmark
    assert repository.calls == 1


def test_warm_premium_benchmark_cache_preloads_age_band_queries(
    monkeypatch: MonkeyPatch,
) -> None:
    benchmark = PremiumBenchmark(
        age_band_label="30대",
        min_age=30,
        max_age=39,
        average_monthly_premium=278395,
        source=PremiumBenchmarkSource(
            label="KB의 생각 · 시그널플래너 40만명 분석",
            url="https://kbthink.com/main/asset-management/insurance/insurance-2-240828.html",
            published_at="2025-06-16",
            reliability="large_private_analysis",
            caveat="평균은 적정 보험료 기준이 아니에요.",
        ),
    )
    repository = _CountingRepository(benchmark)
    monkeypatch.setattr(subject, "_repository", lambda: repository)
    subject._cached_premium_benchmark_for_age.cache_clear()
    monkeypatch.setattr(subject, "_preloaded_benchmarks", None)

    count = subject.warm_premium_benchmark_cache()
    result = subject.premium_benchmark_for_age(35)

    assert count == 1
    assert result == benchmark
    assert repository.calls == 1
