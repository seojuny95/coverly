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
    PortfolioSummaryRequest,
)
from app.modules.portfolio.session.analysis import analyze_portfolio_snapshot
from app.modules.portfolio.session.dependencies import PortfolioSessionServiceDep
from app.modules.portfolio.session.http import resolve_portfolio_snapshot
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
    try:
        snapshot = resolve_portfolio_snapshot(sessions, request)
        summary = analyze_portfolio_snapshot(
            sessions,
            snapshot,
            request,
            summarize,
        )
        try:
            return attach_summary_overview(summary)
        except SummaryOverviewUnavailableError:
            return summary.model_copy(update={"overview": None})
    except ReferenceDataUnavailableError as exc:
        raise ApiError(
            status_code=503,
            code="reference_data_unavailable",
            message="분석 기준 정보를 불러오지 못했어요. 잠시 후 다시 시도해주세요.",
        ) from exc
