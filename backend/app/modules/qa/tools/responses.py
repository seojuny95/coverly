"""Response construction shared by structured portfolio tools."""

from app.modules.evidence.catalog import citation_from_evidence
from app.modules.qa.context import QaContext
from app.modules.qa.contracts import ConsultationEvidence
from app.modules.qa.response_support import (
    contextual_suggestions,
    standard_limitations,
    with_demographics,
)
from app.modules.qa.schemas import PortfolioQuestionResponse


def portfolio_response(
    context: QaContext,
    answer: str,
    evidence: tuple[ConsultationEvidence, ...],
) -> PortfolioQuestionResponse:
    response = PortfolioQuestionResponse(
        status="answered",
        answer=answer,
        citations=[citation_from_evidence(item) for item in evidence],
        limitations=standard_limitations(context.facts),
        suggestions=contextual_suggestions(context),
    )
    return with_demographics(response, context.insured)
