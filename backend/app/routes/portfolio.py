"""HTTP boundary for deterministic portfolio calculations."""

from fastapi import APIRouter

from app.errors import ApiError
from app.schemas.portfolio import PortfolioCoverageSummary, PortfolioSummaryRequest
from app.services.analysis.summary_overview import (
    SummaryOverviewUnavailableError,
    attach_summary_overview,
)
from app.services.portfolio.summary import summarize_portfolio_coverages
from app.services.reference_data import ReferenceDataUnavailableError

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.post("/summary", response_model=PortfolioCoverageSummary)
def coverage_summary(request: PortfolioSummaryRequest) -> PortfolioCoverageSummary:
    try:
        return attach_summary_overview(summarize_portfolio_coverages(request.policies))
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
