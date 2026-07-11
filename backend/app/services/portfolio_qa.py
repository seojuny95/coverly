"""Deterministic portfolio Q&A over structured upload facts."""

from app.schemas.portfolio import PolicyInput
from app.schemas.qa import AnswerCitation, PortfolioQuestionResponse
from app.services.portfolio_summary import (
    PortfolioFacts,
    build_portfolio_facts,
    normalize_coverage_name,
)

_POLICY_TERMS = (
    "보상되",
    "보상 받을",
    "지급 조건",
    "면책",
    "약관",
    "청구",
    "가입 가능",
    "충분",
    "부족",
    "적정",
    "추천",
)
_AMOUNT_TERMS = ("합계", "총액", "얼마", "가입금액")
_STATUS_TERMS = ("상태", "분석", "제외", "확인")
_HOLDING_TERMS = ("몇 개", "몇개", "몇 건", "몇건", "보유", "가입", "목록", "보험")


def answer_portfolio_question(
    question: str, policies: list[PolicyInput]
) -> PortfolioQuestionResponse:
    """Answer supported holdings questions or explicitly refuse unsupported ones."""

    facts = build_portfolio_facts(policies)
    normalized_question = question.strip()
    if not facts.policies:
        return PortfolioQuestionResponse(
            status="no_data",
            answer="업로드된 보험 정보가 없어 답을 확인할 수 없습니다.",
            citations=[],
            limitations=["보험증권을 먼저 업로드해 주세요."],
        )
    if any(term in normalized_question for term in _POLICY_TERMS):
        return _refuse()
    if any(term in normalized_question for term in _AMOUNT_TERMS):
        return _answer_amount(normalized_question, facts)
    if any(term in normalized_question for term in _STATUS_TERMS):
        return _answer_status(facts)
    if any(term in normalized_question for term in _HOLDING_TERMS):
        return _answer_holdings(facts)
    return _refuse()


def _answer_holdings(facts: PortfolioFacts) -> PortfolioQuestionResponse:
    labels: list[str] = []
    for policy in facts.policies:
        insurer = policy.기본정보.보험사 or "보험사 미확인"
        product = policy.기본정보.상품명 or "상품명 미확인"
        classification = policy.기본정보.보험분류 or "미분류"
        labels.append(f"{insurer} {product}({classification})")
    answer = f"업로드된 보험은 {len(labels)}건입니다: {', '.join(labels)}."
    return PortfolioQuestionResponse(
        status="answered",
        answer=answer,
        citations=[_policy_citation(policy) for policy in facts.policies],
        limitations=[],
    )


def _answer_amount(question: str, facts: PortfolioFacts) -> PortfolioQuestionResponse:
    summary = facts.coverage_summary
    selected_totals = summary.totals
    if not _is_overall_amount_question(question):
        normalized_question = normalize_coverage_name(question)
        matches = [
            total for total in summary.totals if total.normalized_name in normalized_question
        ]
        matches.sort(key=lambda total: len(total.normalized_name), reverse=True)
        selected_totals = matches[:1]

    if not selected_totals:
        return PortfolioQuestionResponse(
            status="no_data",
            answer="올린 증권에서 질문한 담보의 확인 가능한 가입금액을 찾지 못했습니다.",
            citations=[],
            limitations=_amount_limitations(facts),
        )

    total_amount = sum(item.total_amount for item in selected_totals)
    citations: list[AnswerCitation] = []
    for total in selected_totals:
        for source in total.composition:
            citations.append(
                AnswerCitation(
                    policy_id=source.policy_id,
                    insurer=source.insurer,
                    product_name=source.product_name,
                    coverage_name=source.coverage_name,
                )
            )
    return PortfolioQuestionResponse(
        status="answered",
        answer=(
            f"확인 가능한 정액형 담보 {len(selected_totals)}종의 합계는 {total_amount:,}원입니다."
        ),
        citations=citations,
        limitations=_amount_limitations(facts),
    )


def _answer_status(facts: PortfolioFacts) -> PortfolioQuestionResponse:
    summary = facts.coverage_summary
    answer = (
        f"보험 {len(facts.policies)}건에서 정액형 합계 {len(summary.totals)}종을 확인했고, "
        f"실손형 {len(summary.indemnity_coverages)}건과 "
        f"합계 제외 {len(summary.excluded_coverages)}건이 있습니다."
    )
    return PortfolioQuestionResponse(
        status="answered",
        answer=answer,
        citations=[_policy_citation(policy) for policy in facts.policies],
        limitations=_amount_limitations(facts),
    )


def _refuse() -> PortfolioQuestionResponse:
    return PortfolioQuestionResponse(
        status="refused",
        answer="업로드된 증권의 구조화 정보만으로는 확인할 수 없습니다.",
        citations=[],
        limitations=[
            "보상 조건·면책·적정성 판단은 약관 근거가 필요하며 현재 Q&A 범위에 포함되지 않습니다."
        ],
    )


def _amount_limitations(facts: PortfolioFacts) -> list[str]:
    summary = facts.coverage_summary
    limitations: list[str] = []
    if summary.indemnity_coverages:
        limitations.append("실손형 담보는 합산하지 않았습니다.")
    if summary.excluded_coverages:
        limitations.append("지급유형 또는 금액이 확인되지 않은 담보는 합산하지 않았습니다.")
    if summary.excluded_auto_policy_count:
        limitations.append("자동차 보험은 합산하지 않았습니다.")
    return limitations


def _is_overall_amount_question(question: str) -> bool:
    return "전체" in question or "총합" in question


def _policy_citation(policy: PolicyInput) -> AnswerCitation:
    return AnswerCitation(
        policy_id=policy.id,
        insurer=policy.기본정보.보험사,
        product_name=policy.기본정보.상품명,
    )
