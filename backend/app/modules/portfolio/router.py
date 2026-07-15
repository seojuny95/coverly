"""HTTP boundary for deterministic portfolio calculations."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.errors import ApiError
from app.modules.analysis.summary_overview import (
    SummaryOverviewUnavailableError,
    attach_summary_overview,
)
from app.modules.portfolio.schemas import (
    PolicyInput,
    PortfolioCoverageSummary,
    PortfolioSummaryRequest,
)
from app.modules.portfolio.summary import summarize_portfolio_coverages
from app.modules.reference_data.loader import ReferenceDataUnavailableError

router = APIRouter(prefix="/portfolio", tags=["portfolio"])

PortfolioSummaryService = Callable[[list[PolicyInput]], PortfolioCoverageSummary]


def build_portfolio_summary(policies: list[PolicyInput]) -> PortfolioCoverageSummary:
    summary = summarize_portfolio_coverages(policies)
    return attach_summary_overview(summary)


def get_portfolio_summary_service() -> PortfolioSummaryService:
    return build_portfolio_summary


PortfolioSummaryServiceDep = Annotated[
    PortfolioSummaryService,
    Depends(get_portfolio_summary_service),
]


@router.post("/summary", response_model=PortfolioCoverageSummary)
def coverage_summary(
    request: PortfolioSummaryRequest,
    summarize: PortfolioSummaryServiceDep,
) -> PortfolioCoverageSummary:
    try:
        return summarize(request.policies)
    except ReferenceDataUnavailableError as exc:
        raise ApiError(
            status_code=503,
            code="reference_data_unavailable",
            message="분석 기준 정보를 불러오지 못했어요. 잠시 후 다시 시도해주세요.",
        ) from exc
    except SummaryOverviewUnavailableError as exc:
        raise ApiError(
            status_code=503,
            code="portfolio_overview_unavailable",
            message="전체 보험 총평을 생성하지 못했어요. 잠시 후 다시 시도해주세요.",
        ) from exc
