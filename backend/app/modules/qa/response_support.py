"""Shared response metadata for grounded QA paths."""

from app.modules.consultation.contracts import InsuredDemographics
from app.modules.portfolio.summary import PortfolioFacts
from app.modules.qa.context import QaContext
from app.modules.qa.schemas import PortfolioQuestionResponse

_MAX_SUGGESTIONS = 3


def contextual_suggestions(context: QaContext) -> list[str]:
    totals = context.facts.coverage_summary.totals
    candidates = ["가입한 보험은 몇 개야?"]
    if totals:
        coverage_name = totals[0].display_name
        candidates[:0] = [
            f"{coverage_name} 가입금액은 얼마야?",
            f"{coverage_name} 지급 조건은 뭐야?",
        ]
    if any(
        item.is_medical_indemnity for item in context.facts.coverage_summary.actual_loss_coverages
    ):
        candidates.append("실손의료비 청구는 어디서 해?")
    return question_suggestions(*candidates)


def question_suggestions(*candidates: str) -> list[str]:
    suggestions: list[str] = []
    for candidate in candidates:
        cleaned = " ".join(candidate.split())
        if not cleaned or cleaned in suggestions or not cleaned.endswith("?"):
            continue
        suggestions.append(cleaned)
        if len(suggestions) == _MAX_SUGGESTIONS:
            break
    return suggestions


def standard_limitations(facts: PortfolioFacts) -> list[str]:
    summary = facts.coverage_summary
    limitations = ["보상 조건·면책·지급 가능성은 약관 근거 없이 판단하지 않습니다."]
    if summary.actual_loss_coverages:
        limitations.append("실손형 담보는 가입금액 합계에 포함하지 않았습니다.")
    if summary.excluded_coverages:
        limitations.append("지급유형 또는 금액이 확인되지 않은 담보는 합계에 포함하지 않았습니다.")
    if summary.damage_coverages:
        limitations.append(
            "손해보험은 종류별 보장금으로 따로 표시하고 가입금액 합계에는 포함하지 않았어요."
        )
    return limitations


def demographic_notice(demographics: InsuredDemographics) -> str | None:
    return {
        "conflict": "증권별 피보험자 정보가 서로 달라 나이·성별 개인화를 적용하지 않았습니다.",
        "conflict_user_override": (
            "증권별 피보험자 정보가 서로 달라 사용자가 확인한 정보로 개인화했습니다."
        ),
        "missing": "증권에서 피보험자 나이·성별을 확인하지 못해 개인화를 적용하지 않았습니다.",
    }.get(demographics.status)


def with_demographics(
    response: PortfolioQuestionResponse,
    demographics: InsuredDemographics,
) -> PortfolioQuestionResponse:
    limitations = list(response.limitations)
    notice = demographic_notice(demographics)
    if notice and notice not in limitations:
        limitations.append(notice)
    return response.model_copy(update={"demographics": demographics, "limitations": limitations})


def agent_unavailable_response(context: QaContext) -> PortfolioQuestionResponse:
    return with_demographics(
        PortfolioQuestionResponse(
            status="no_data",
            answer=(
                "지금은 질문에 필요한 근거 조회를 완료하지 못했어요. "
                "확인되지 않은 내용으로 대신 답하지 않았습니다."
            ),
            citations=[],
            limitations=["Agent 또는 근거 조회가 완료되지 않았습니다."],
            suggestions=[],
        ),
        context.insured,
    )


def out_of_scope_response(context: QaContext) -> PortfolioQuestionResponse:
    return with_demographics(
        PortfolioQuestionResponse(
            status="refused",
            answer=(
                "이 질문은 보험 상담 범위 밖이라 답하기 어려워요. "
                "저는 보험과 올려주신 증권을 함께 살펴보는 상담을 도와드려요. "
                "가입 보험, 담보, 가입금액, 약관, 청구처럼 보험과 관련된 내용으로 물어봐 주세요."
            ),
            citations=[],
            limitations=["보험 상담 범위 밖의 질문에는 답하지 않습니다."],
            suggestions=[],
        ),
        context.insured,
    )
