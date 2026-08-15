"""HTTP boundary for deterministic portfolio calculations."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.errors import ApiError, api_error_responses
from app.modules.portfolio.overview import (
    SummaryOverviewUnavailableError,
    attach_summary_overview,
)
from app.modules.portfolio.schemas import (
    DeathBenefitGuideInput,
    PolicyInput,
    PortfolioCoverageSummary,
    PortfolioOverview,
    PortfolioSummaryRequest,
)
from app.modules.portfolio.session.analysis import (
    SamplePortfolioFixtureUnavailable,
    analysis_context_hash,
    analyze_portfolio_snapshot,
)
from app.modules.portfolio.session.dependencies import PortfolioSessionServiceDep
from app.modules.portfolio.session.http import (
    portfolio_session_unavailable_error,
    resolve_portfolio_snapshot,
)
from app.modules.portfolio.session.models import (
    CachedPortfolioAnalysis,
    PortfolioSessionSnapshot,
)
from app.modules.portfolio.session.service import PortfolioSessionUnavailable
from app.modules.portfolio.summary import summarize_portfolio_coverages
from app.modules.reference_data.loader import ReferenceDataUnavailableError

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


class PortfolioSummaryService:
    def __call__(
        self,
        policies: list[PolicyInput],
        death_benefit_context: DeathBenefitGuideInput,
    ) -> PortfolioCoverageSummary:
        return summarize_portfolio_coverages(policies, death_benefit_context)


def get_portfolio_summary_service() -> PortfolioSummaryService:
    return PortfolioSummaryService()


PortfolioSummaryServiceDep = Annotated[
    PortfolioSummaryService,
    Depends(get_portfolio_summary_service),
]


@router.post(
    "/summary",
    response_model=PortfolioCoverageSummary,
    responses=api_error_responses(403, 503),
)
def coverage_summary(
    request: PortfolioSummaryRequest,
    summarize: PortfolioSummaryServiceDep,
    sessions: PortfolioSessionServiceDep,
) -> PortfolioCoverageSummary:
    summary, _, _ = _portfolio_analysis(request, summarize, sessions)
    return summary.model_copy(update={"overview": None})


@router.post(
    "/overview",
    response_model=PortfolioOverview,
    responses=api_error_responses(403, 503),
)
def summary_overview(
    request: PortfolioSummaryRequest,
    summarize: PortfolioSummaryServiceDep,
    sessions: PortfolioSessionServiceDep,
) -> PortfolioOverview:
    summary, snapshot, context_hash = _portfolio_analysis(request, summarize, sessions)
    if summary.overview is not None:
        return summary.overview
    try:
        summary_with_overview = attach_summary_overview(summary)
        overview = summary_with_overview.overview
    except SummaryOverviewUnavailableError as exc:
        raise ApiError(
            status_code=503,
            code="portfolio_overview_unavailable",
            message=(
                "총평을 생성하지 못했어요. 확인된 보장 정보는 그대로 있어요. "
                "잠시 후 다시 시도해주세요."
            ),
        ) from exc
    if overview is None:
        raise ApiError(
            status_code=503,
            code="portfolio_overview_unavailable",
            message=(
                "총평을 생성하지 못했어요. 확인된 보장 정보는 그대로 있어요. "
                "잠시 후 다시 시도해주세요."
            ),
        )
    sessions.save_cached_analysis(
        snapshot,
        CachedPortfolioAnalysis(
            version=snapshot.version,
            context_hash=context_hash,
            result=summary_with_overview.model_dump(mode="json"),
        ),
    )
    return overview


def _portfolio_analysis(
    request: PortfolioSummaryRequest,
    summarize: PortfolioSummaryService,
    sessions: PortfolioSessionServiceDep,
) -> tuple[PortfolioCoverageSummary, PortfolioSessionSnapshot, str]:
    try:
        snapshot = resolve_portfolio_snapshot(sessions, request)
        summary = analyze_portfolio_snapshot(
            sessions,
            snapshot,
            request,
            summarize,
        )
        return summary, snapshot, analysis_context_hash(request)
    except ReferenceDataUnavailableError as exc:
        raise ApiError(
            status_code=503,
            code="reference_data_unavailable",
            message="분석 기준 정보를 불러오지 못했어요. 잠시 후 다시 시도해주세요.",
        ) from exc
    except PortfolioSessionUnavailable:
        raise portfolio_session_unavailable_error() from None
    except SamplePortfolioFixtureUnavailable:
        raise ApiError(
            status_code=503,
            code="sample_portfolio_unavailable",
            message="샘플 분석을 불러오지 못했어요. 잠시 후 다시 시도해주세요.",
        ) from None
