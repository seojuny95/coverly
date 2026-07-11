"""Thin HTTP route for deterministic portfolio analysis."""

from fastapi import APIRouter

from app.schemas.analysis import PortfolioAnalysisRequest, PortfolioAnalysisResponse
from app.services.portfolio_analysis import analyze_portfolio

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.post("/analysis", response_model=PortfolioAnalysisResponse)
def create_portfolio_analysis(request: PortfolioAnalysisRequest) -> PortfolioAnalysisResponse:
    return analyze_portfolio(
        request.policies,
        demographics=request.resolved_demographics(),
    )
