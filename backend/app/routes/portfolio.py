"""HTTP boundary for deterministic portfolio calculations."""

from fastapi import APIRouter

from app.schemas.portfolio import PortfolioCoverageSummary, PortfolioSummaryRequest
from app.services.portfolio_summary import summarize_portfolio_coverages

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.post("/summary", response_model=PortfolioCoverageSummary)
def coverage_summary(request: PortfolioSummaryRequest) -> PortfolioCoverageSummary:
    return summarize_portfolio_coverages(request.policies)
