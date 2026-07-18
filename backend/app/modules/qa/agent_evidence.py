"""Evidence selection helpers for grounded QA agent tools."""

from app.modules.coverage.matching import canonicalize_coverage_name, query_contains_canonical_name
from app.modules.coverage.taxonomy import CANCER, classify_coverage
from app.modules.qa.context import QaContext
from app.modules.qa.contracts import ConsultationEvidence
from app.modules.qa.schemas import PortfolioQuestionResponse

_OVERLAP_QUESTION_TERMS = ("겹치", "중복")
_OVERLAP_EVIDENCE_TERMS = (
    "같은 담보명",
    "여러 계약에서 같은 실손형",
)
_BROAD_PORTFOLIO_TERMS = (
    "강점",
    "약점",
    "부족",
    "비어",
    "전체",
    "정리",
    "분석",
    "어떻게 봐",
    "보험료",
    "유지",
    "해지",
)
_SECONDARY_CANCER_COVERAGE_TERMS = ("유사암", "재진단", "전이암", "소액암")


def consultation_evidence(context: QaContext) -> tuple[ConsultationEvidence, ...]:
    question = context.question
    if any(term in question for term in _OVERLAP_QUESTION_TERMS):
        return tuple(
            item
            for item in context.catalog.items
            if item.id == "portfolio:no-overlap"
            or any(term in item.fact for term in _OVERLAP_EVIDENCE_TERMS)
        )
    if any(term in question for term in _BROAD_PORTFOLIO_TERMS):
        return context.catalog.items

    evidence_ids: list[str] = []
    category = classify_coverage(question)
    if category is None and "암" in "".join(question.split()):
        category = CANCER
    if category is not None:
        evidence_ids.extend(context.catalog.coverage_ids_by_category.get(category, ()))

    for item in context.catalog.items:
        coverage_key = (
            canonicalize_coverage_name(item.coverage_name).normalized_key
            if item.coverage_name
            else None
        )
        if (
            (coverage_key and query_contains_canonical_name(question, coverage_key))
            or (item.insurer and item.insurer in question)
            or (item.product_name and item.product_name in question)
        ):
            evidence_ids.append(item.id)

    evidence = tuple(
        context.catalog.by_id[evidence_id]
        for evidence_id in dict.fromkeys(evidence_ids)
        if evidence_id in context.catalog.by_id
    )
    if category == CANCER and "유사암" not in question:
        primary = tuple(
            item
            for item in evidence
            if item.coverage_name is None
            or not any(
                term in item.coverage_name.split("(")[0].strip()
                for term in _SECONDARY_CANCER_COVERAGE_TERMS
            )
        )
        return primary or evidence
    return evidence


def portfolio_snapshot_evidence(
    context: QaContext,
    *,
    max_items: int = 24,
) -> tuple[ConsultationEvidence, ...]:
    """Return a bounded portfolio snapshot for agent-led consultation fallback."""

    return context.catalog.items[:max_items]


def response_evidence(
    context: QaContext,
    response: PortfolioQuestionResponse,
) -> tuple[ConsultationEvidence, ...]:
    evidence: list[ConsultationEvidence] = []
    for citation in response.citations:
        if citation.evidence_id is None:
            continue
        item = context.catalog.by_id.get(citation.evidence_id)
        if item is not None:
            evidence.append(item)
    return tuple(evidence)
