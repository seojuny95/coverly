from collections.abc import Iterator

from pytest import MonkeyPatch, fixture

from app.modules.portfolio.schemas import PremiumBenchmark, PremiumBenchmarkSource
from app.modules.reference_data import premium_benchmark as subject


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


class _FailingRepository:
    def __init__(self) -> None:
        self.find_calls = 0
        self.list_calls = 0

    def find_by_age(self, age: int | None) -> PremiumBenchmark | None:
        self.find_calls += 1
        raise RuntimeError("database unavailable")

    def list_all(self) -> tuple[PremiumBenchmark, ...]:
        self.list_calls += 1
        raise RuntimeError("database unavailable")


class _RecoveringRepository:
    def __init__(self, benchmark: PremiumBenchmark) -> None:
        self.benchmark = benchmark
        self.list_calls = 0
        self.find_calls = 0

    def find_by_age(self, age: int | None) -> PremiumBenchmark | None:
        self.find_calls += 1
        return self.benchmark if age == 35 else None

    def list_all(self) -> tuple[PremiumBenchmark, ...]:
        self.list_calls += 1
        raise RuntimeError("database temporarily unavailable")


@fixture(autouse=True)
def _reset_cache_state(monkeypatch: MonkeyPatch) -> Iterator[None]:
    subject._cached_premium_benchmark_for_age.cache_clear()
    monkeypatch.setattr(subject, "_preloaded_benchmarks", None)
    monkeypatch.setattr(subject, "_failure_retry_at", None)
    yield
    subject._cached_premium_benchmark_for_age.cache_clear()


def test_premium_benchmark_lookup_caches_successful_age_queries(
    monkeypatch: MonkeyPatch,
) -> None:
    benchmark = PremiumBenchmark(
        age_band_label="30~39세",
        min_age=30,
        max_age=39,
        average_monthly_income=3_860_000,
        suggested_min_ratio=0.05,
        suggested_max_ratio=0.10,
        suggested_min_premium=193_000,
        suggested_max_premium=386_000,
        income_source=PremiumBenchmarkSource(
            label="KOSIS 국가통계포털 · 성별 연령대별 소득",
            url="https://kosis.kr/statHtml/statHtml.do?sso=ok&returnurl=https%3A%2F%2Fkosis.kr%3A443%2FstatHtml%2FstatHtml.do%3Fconn_path%3DI2%26tblId%3DDT_1EP_2010%26orgId%3D101%26",
            published_at="2025-01-01",
            reliability="official",
            caveat="연령대 평균 소득은 개인 소득과 다를 수 있어요.",
        ),
        guide_source=PremiumBenchmarkSource(
            label="뱅크샐러드 · 나에게 맞는 보험료 계산법",
            url="https://www.banksalad.com/articles/%EB%B3%B4%ED%97%98-%EB%B3%B4%ED%97%98%EB%A6%AC%EB%AA%A8%EB%8D%B8%EB%A7%81-%EB%B3%B4%ED%97%98%EB%A3%8C",
            published_at="2025-01-01",
            reliability="private_guidance",
            caveat="월 소득의 5%~10% 범위는 민간 가이드예요. 적정 보험료의 공식 기준은 아니에요.",
        ),
    )
    repository = _CountingRepository(benchmark)
    monkeypatch.setattr(subject, "_repository", lambda: repository)
    first = subject.premium_benchmark_for_age(35)
    second = subject.premium_benchmark_for_age(35)

    assert first == benchmark
    assert second == benchmark
    assert repository.calls == 1


def test_warm_premium_benchmark_cache_preloads_age_band_queries(
    monkeypatch: MonkeyPatch,
) -> None:
    benchmark = PremiumBenchmark(
        age_band_label="30~39세",
        min_age=30,
        max_age=39,
        average_monthly_income=3_860_000,
        suggested_min_ratio=0.05,
        suggested_max_ratio=0.10,
        suggested_min_premium=193_000,
        suggested_max_premium=386_000,
        income_source=PremiumBenchmarkSource(
            label="KOSIS 국가통계포털 · 성별 연령대별 소득",
            url="https://kosis.kr/statHtml/statHtml.do?sso=ok&returnurl=https%3A%2F%2Fkosis.kr%3A443%2FstatHtml%2FstatHtml.do%3Fconn_path%3DI2%26tblId%3DDT_1EP_2010%26orgId%3D101%26",
            published_at="2025-01-01",
            reliability="official",
            caveat="연령대 평균 소득은 개인 소득과 다를 수 있어요.",
        ),
        guide_source=PremiumBenchmarkSource(
            label="뱅크샐러드 · 나에게 맞는 보험료 계산법",
            url="https://www.banksalad.com/articles/%EB%B3%B4%ED%97%98-%EB%B3%B4%ED%97%98%EB%A6%AC%EB%AA%A8%EB%8D%B8%EB%A7%81-%EB%B3%B4%ED%97%98%EB%A3%8C",
            published_at="2025-01-01",
            reliability="private_guidance",
            caveat="월 소득의 5%~10% 범위는 민간 가이드예요. 적정 보험료의 공식 기준은 아니에요.",
        ),
    )
    repository = _CountingRepository(benchmark)
    monkeypatch.setattr(subject, "_repository", lambda: repository)
    count = subject.warm_premium_benchmark_cache()
    result = subject.premium_benchmark_for_age(35)

    assert count == 1
    assert result == benchmark
    assert repository.calls == 1


def test_premium_benchmark_lookup_does_not_invent_fallback_data(
    monkeypatch: MonkeyPatch,
) -> None:
    repository = _FailingRepository()
    monkeypatch.setattr(subject, "_repository", lambda: repository)

    assert subject.premium_benchmark_for_age(35) is None
    assert subject.premium_benchmark_for_age(35) is None
    assert repository.find_calls == 1


def test_failed_warm_premium_benchmark_cache_retries_on_a_later_request(
    monkeypatch: MonkeyPatch,
) -> None:
    benchmark = PremiumBenchmark(
        age_band_label="30~39세",
        min_age=30,
        max_age=39,
        average_monthly_income=3_860_000,
        suggested_min_ratio=0.05,
        suggested_max_ratio=0.10,
        suggested_min_premium=193_000,
        suggested_max_premium=386_000,
        income_source=PremiumBenchmarkSource(
            label="소득 자료",
            url="https://example.com/income",
            published_at="2025-01-01",
            reliability="official",
            caveat="개인 소득과 다를 수 있어요.",
        ),
        guide_source=PremiumBenchmarkSource(
            label="보험료 가이드",
            url="https://example.com/guide",
            published_at="2025-01-01",
            reliability="private_guidance",
            caveat="일반 가이드예요.",
        ),
    )
    repository = _RecoveringRepository(benchmark)
    now = [100.0]
    monkeypatch.setattr(subject, "_repository", lambda: repository)
    monkeypatch.setattr(subject, "monotonic", lambda: now[0])

    assert subject.warm_premium_benchmark_cache() == 0
    assert subject.premium_benchmark_for_age(35) is None
    assert repository.find_calls == 0

    now[0] += subject._FAILURE_BACKOFF_SECONDS

    assert subject.premium_benchmark_for_age(35) == benchmark
    assert repository.list_calls == 1
    assert repository.find_calls == 1


def test_persistent_failure_retries_only_once_per_backoff_window(
    monkeypatch: MonkeyPatch,
) -> None:
    repository = _FailingRepository()
    now = [100.0]
    monkeypatch.setattr(subject, "_repository", lambda: repository)
    monkeypatch.setattr(subject, "monotonic", lambda: now[0])

    assert subject.warm_premium_benchmark_cache() == 0
    assert subject.premium_benchmark_for_age(35) is None
    assert subject.premium_benchmark_for_age(45) is None
    assert repository.list_calls == 1
    assert repository.find_calls == 0

    now[0] += subject._FAILURE_BACKOFF_SECONDS

    assert subject.premium_benchmark_for_age(35) is None
    assert subject.premium_benchmark_for_age(45) is None
    assert repository.find_calls == 1

    now[0] += subject._FAILURE_BACKOFF_SECONDS

    assert subject.premium_benchmark_for_age(35) is None
    assert repository.find_calls == 2
