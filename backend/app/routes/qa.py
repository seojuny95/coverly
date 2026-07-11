"""Thin HTTP route for non-RAG portfolio questions."""

from fastapi import APIRouter

from app.schemas.qa import PortfolioQuestionRequest, PortfolioQuestionResponse
from app.services.portfolio_qa import answer_portfolio_question

router = APIRouter(tags=["qa"])


@router.post("/qa", response_model=PortfolioQuestionResponse)
def ask_portfolio_question(request: PortfolioQuestionRequest) -> PortfolioQuestionResponse:
    return answer_portfolio_question(request.question, request.policies)
