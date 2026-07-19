from pytest import MonkeyPatch

from app.modules.portfolio.schemas import PortfolioSummaryRequest
from app.modules.portfolio.session import analysis


def test_analysis_cache_hash_changes_with_implementation_version(
    monkeypatch: MonkeyPatch,
) -> None:
    request = PortfolioSummaryRequest.model_validate(
        {
            "portfolioSessionToken": "portfolio-token",
            "policyIds": ["00000000-0000-0000-0000-000000000001"],
        }
    )
    current_hash = analysis._analysis_context_hash(request)

    monkeypatch.setattr(
        analysis,
        "PORTFOLIO_ANALYSIS_CACHE_VERSION",
        analysis.PORTFOLIO_ANALYSIS_CACHE_VERSION + 1,
    )

    assert analysis._analysis_context_hash(request) != current_hash
