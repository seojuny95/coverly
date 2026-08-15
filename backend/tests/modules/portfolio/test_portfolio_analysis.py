from typing import cast

import pytest
from pytest import MonkeyPatch

from app.modules.portfolio.schemas import (
    CoverageTotalItem,
    DeathBenefitGuideInput,
    PolicyInput,
    PortfolioCoverageSummary,
    PortfolioSummaryRequest,
)
from app.modules.portfolio.session import analysis
from app.modules.portfolio.session.models import (
    CachedPortfolioAnalysis,
    PortfolioSessionSnapshot,
)
from app.modules.portfolio.session.service import PortfolioSessionService


def test_analysis_cache_hash_changes_with_implementation_version(
    monkeypatch: MonkeyPatch,
) -> None:
    request = PortfolioSummaryRequest.model_validate(
        {
            "portfolioSessionToken": "portfolio-token",
            "policyIds": ["00000000-0000-0000-0000-000000000001"],
        }
    )
    current_hash = analysis.analysis_context_hash(request)

    monkeypatch.setattr(
        analysis,
        "PORTFOLIO_ANALYSIS_CACHE_VERSION",
        analysis.PORTFOLIO_ANALYSIS_CACHE_VERSION + 1,
    )

    assert analysis.analysis_context_hash(request) != current_hash


def test_cached_analysis_round_trips_and_replaces_invalid_payloads() -> None:
    request = PortfolioSummaryRequest.model_validate(
        {
            "portfolioSessionToken": "portfolio-token",
            "policyIds": ["00000000-0000-0000-0000-000000000001"],
        }
    )
    snapshot = PortfolioSessionSnapshot(
        session_id="portfolio-1",
        version=1,
        policies=(),
        rag_session_ids=(),
    )
    expected = PortfolioCoverageSummary(
        totals=[
            CoverageTotalItem(
                normalized_name="암진단비",
                display_name="암진단비",
                major_category="진단",
                total_amount=30_000_000,
                coverage_count=1,
                composition=[],
            )
        ],
        actual_loss_coverages=[],
        excluded_coverages=[],
        excluded_auto_policy_count=0,
    )

    class Sessions:
        cached: CachedPortfolioAnalysis | None = None

        def load_cached_analysis(
            self,
            _snapshot: PortfolioSessionSnapshot,
            *,
            context_hash: str,
        ) -> CachedPortfolioAnalysis | None:
            if self.cached is None or self.cached.context_hash != context_hash:
                return None
            return self.cached

        def save_cached_analysis(
            self,
            _snapshot: PortfolioSessionSnapshot,
            cached: CachedPortfolioAnalysis,
        ) -> None:
            self.cached = cached

    sessions = Sessions()
    calculate_calls = 0

    def calculate(
        _policies: list[PolicyInput],
        _context: DeathBenefitGuideInput,
    ) -> PortfolioCoverageSummary:
        nonlocal calculate_calls
        calculate_calls += 1
        return expected

    session_service = cast(PortfolioSessionService, sessions)
    first = analysis.analyze_portfolio_snapshot(
        session_service,
        snapshot,
        request,
        calculate,
    )
    second = analysis.analyze_portfolio_snapshot(
        session_service,
        snapshot,
        request,
        calculate,
    )

    assert first == expected
    assert second == expected
    assert calculate_calls == 1
    assert sessions.cached is not None
    assert sessions.cached.result == expected.model_dump(mode="json")

    sessions.cached = CachedPortfolioAnalysis(
        version=sessions.cached.version,
        context_hash=sessions.cached.context_hash,
        result={"totals": []},
    )
    recovered = analysis.analyze_portfolio_snapshot(
        session_service,
        snapshot,
        request,
        calculate,
    )

    assert recovered == expected
    assert calculate_calls == 2
    assert sessions.cached.result == expected.model_dump(mode="json")


def test_sample_analysis_never_falls_back_to_live_calculation() -> None:
    request = PortfolioSummaryRequest.model_validate(
        {
            "portfolioSessionToken": "sample-token",
            "policyIds": ["00000000-0000-0000-0000-000000000001"],
        }
    )
    snapshot = PortfolioSessionSnapshot(
        session_id="sample-1",
        version=1,
        policies=(),
        rag_session_ids=(),
        kind="sample",
    )

    class Sessions:
        def load_cached_analysis(
            self,
            _snapshot: PortfolioSessionSnapshot,
            *,
            context_hash: str,
        ) -> None:
            return None

    def calculate(
        _policies: list[PolicyInput],
        _context: DeathBenefitGuideInput,
    ) -> PortfolioCoverageSummary:
        raise AssertionError("sample cache misses must not calculate live")

    with pytest.raises(analysis.SamplePortfolioFixtureUnavailable):
        analysis.analyze_portfolio_snapshot(
            cast(PortfolioSessionService, Sessions()),
            snapshot,
            request,
            calculate,
        )
