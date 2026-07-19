"""Cached portfolio analysis orchestration for stored sessions."""

import hashlib
import json
from collections.abc import Callable

from app.modules.portfolio.schemas import (
    DeathBenefitGuideInput,
    PolicyInput,
    PortfolioCoverageSummary,
    PortfolioSummaryRequest,
)
from app.modules.portfolio.session.models import (
    CachedPortfolioAnalysis,
    PortfolioSessionSnapshot,
)
from app.modules.portfolio.session.service import PortfolioSessionService

PortfolioSummaryCalculator = Callable[
    [list[PolicyInput], DeathBenefitGuideInput],
    PortfolioCoverageSummary,
]

PORTFOLIO_ANALYSIS_CACHE_VERSION = 2


def analyze_portfolio_snapshot(
    sessions: PortfolioSessionService,
    snapshot: PortfolioSessionSnapshot,
    request: PortfolioSummaryRequest,
    calculate: PortfolioSummaryCalculator,
) -> PortfolioCoverageSummary:
    context_hash = _analysis_context_hash(request)
    cached = sessions.load_cached_analysis(snapshot, context_hash=context_hash)
    if cached is not None:
        return PortfolioCoverageSummary.model_validate(cached.result)

    result = calculate(list(snapshot.policies), request.death_benefit_context)
    sessions.save_cached_analysis(
        snapshot,
        CachedPortfolioAnalysis(
            version=snapshot.version,
            context_hash=context_hash,
            result=result.model_dump(mode="json", by_alias=True),
        ),
    )
    return result


def _analysis_context_hash(request: PortfolioSummaryRequest) -> str:
    payload = {
        "analysis_version": PORTFOLIO_ANALYSIS_CACHE_VERSION,
        "policy_ids": request.policy_id_strings(),
        "death_benefit_context": request.death_benefit_context.model_dump(mode="json"),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode()).hexdigest()
