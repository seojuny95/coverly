"""Compose planned QA turns from scope and insurance answer strategies."""

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from app.integrations.openai.client import JsonCompleter
from app.modules.qa.context import QaContext, context_with_question
from app.modules.qa.contracts import GenerationMode
from app.modules.qa.planning import PlannedQuestion, QuestionPlan
from app.modules.qa.resolvers import (
    OfficialAnswerer,
    contextual_suggestions,
    question_suggestions,
)
from app.modules.qa.schemas import AnswerCitation, ClaimChannelBlock, PortfolioQuestionResponse

_GREETING_ANSWER = "**안녕하세요.** 가입한 보험과 보장에 관해 궁금한 내용을 물어봐 주세요."
_OUT_OF_SCOPE_ANSWER = (
    "**보험과 관련 없는 정보**는 답변하기 어려워요.\n\n"
    "- 가입 보험, 보장, 약관, 청구와 관련된 질문은 도와드릴 수 있어요."
)

ContextAnswerer = Callable[
    [QaContext, JsonCompleter | None, OfficialAnswerer | None],
    PortfolioQuestionResponse,
]


def clarification_response(question: str) -> PortfolioQuestionResponse:
    return PortfolioQuestionResponse(
        status="clarify",
        answer=_markdown_section("확인이 필요해요", question),
        citations=[],
        limitations=[],
        suggestions=[],
    )


def is_scope_only_plan(question_plan: QuestionPlan) -> bool:
    return all(planned.scope != "insurance" for planned in question_plan.questions)


def answer_scope_only_plan(question_plan: QuestionPlan) -> PortfolioQuestionResponse:
    answers: list[str] = []
    answered = False
    for planned in question_plan.questions:
        answer, planned_answered = _scope_answer(planned)
        answered = answered or planned_answered
        _append_planned_answer(answers, len(question_plan.questions), planned, answer)

    return PortfolioQuestionResponse(
        status="answered" if answered else "refused",
        answer="\n\n".join(answers),
        citations=[],
        limitations=[],
        suggestions=[],
    )


def answer_question_plan(
    context: QaContext,
    question_plan: QuestionPlan,
    complete: JsonCompleter | None,
    official_answer: OfficialAnswerer | None,
    answer_context: ContextAnswerer,
) -> PortfolioQuestionResponse:
    if question_plan.clarification is not None:
        return clarification_response(question_plan.clarification)

    answers: list[str] = []
    citations: list[AnswerCitation] = []
    limitations: list[str] = []
    suggestions: list[str] = []
    answered = False
    generation: GenerationMode = "fallback"
    claim_channels: ClaimChannelBlock | None = None
    insurance_answers = _answer_insurance_questions(
        context,
        question_plan,
        complete,
        official_answer,
        answer_context,
    )

    for index, planned in enumerate(question_plan.questions):
        if planned.scope == "insurance":
            response = insurance_answers[index]
            answer = response.answer
            answered = answered or response.status == "answered"
            generation = "llm" if response.generation == "llm" else generation
            citations.extend(response.citations)
            limitations.extend(response.limitations)
            suggestions.extend(response.suggestions)
            claim_channels = claim_channels or response.claim_channels
        else:
            answer, planned_answered = _scope_answer(planned)
            answered = answered or planned_answered
        _append_planned_answer(answers, len(question_plan.questions), planned, answer)

    return PortfolioQuestionResponse(
        status="answered" if answered else "refused",
        answer="\n\n".join(answers),
        citations=_unique_citations(citations),
        limitations=list(dict.fromkeys(limitations)),
        suggestions=question_suggestions(*suggestions, *contextual_suggestions(context)),
        generation=generation,
        demographics=context.insured,
        claim_channels=claim_channels,
    )


def _answer_insurance_questions(
    context: QaContext,
    question_plan: QuestionPlan,
    complete: JsonCompleter | None,
    official_answer: OfficialAnswerer | None,
    answer_context: ContextAnswerer,
) -> dict[int, PortfolioQuestionResponse]:
    insurance_tasks = [
        (index, planned)
        for index, planned in enumerate(question_plan.questions)
        if planned.scope == "insurance"
    ]
    if not insurance_tasks:
        return {}
    if len(insurance_tasks) == 1:
        index, planned = insurance_tasks[0]
        return {
            index: answer_context(
                context_with_question(context, planned.resolved),
                complete,
                official_answer,
            )
        }

    with ThreadPoolExecutor(max_workers=len(insurance_tasks)) as executor:
        futures = {
            index: executor.submit(
                answer_context,
                context_with_question(context, planned.resolved),
                complete,
                official_answer,
            )
            for index, planned in insurance_tasks
        }
        return {index: future.result() for index, future in futures.items()}


def _scope_answer(planned: PlannedQuestion) -> tuple[str, bool]:
    if planned.scope == "greeting":
        return _GREETING_ANSWER, True
    return _OUT_OF_SCOPE_ANSWER, False


def _append_planned_answer(
    answers: list[str],
    question_count: int,
    planned: PlannedQuestion,
    answer: str,
) -> None:
    if question_count == 1:
        answers.append(answer)
    else:
        answers.append(f"**{planned.original}**\n\n{answer}")


def _unique_citations(citations: list[AnswerCitation]) -> list[AnswerCitation]:
    unique: list[AnswerCitation] = []
    seen: set[str] = set()
    for citation in citations:
        key = citation.model_dump_json()
        if key in seen:
            continue
        seen.add(key)
        unique.append(citation)
    return unique


def _markdown_section(title: str, content: str) -> str:
    return f"**{title}**\n\n{content.strip()}"
