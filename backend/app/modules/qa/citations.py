"""Map provider-neutral consultation evidence to the public QA contract."""

from app.modules.consultation.contracts import ConsultationEvidence
from app.modules.qa.schemas import AnswerCitation


def citation_from_evidence(item: ConsultationEvidence) -> AnswerCitation:
    return AnswerCitation(
        evidence_id=item.id,
        policy_id=item.policy_id,
        insurer=item.insurer,
        product_name=item.product_name,
        coverage_name=item.coverage_name,
    )
