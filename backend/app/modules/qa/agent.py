"""Agent SDK orchestration for grounded portfolio Q&A."""

import asyncio
from collections.abc import Iterator
from queue import Queue
from threading import Thread
from typing import Any

from agents import (
    Agent,
    GuardrailFunctionOutput,
    ModelSettings,
    RunConfig,
    RunContextWrapper,
    RunHooks,
    Runner,
    output_guardrail,
)
from agents.models.openai_provider import OpenAIProvider

from app.core.config import get_settings
from app.integrations.openai.client import JsonCompleter
from app.modules.policy.demographics import mask_demographic_identifiers
from app.modules.qa.agent_contracts import (
    AgentCounselorDraft,
    QaAgentCompleted,
    QaAgentDependencies,
    QaAgentProgress,
    QaAgentRunner,
    QaAgentStreamItem,
    QaAgentUnavailable,
)
from app.modules.qa.agent_tools import (
    answer_from_grounded_qa_tools,
    answer_from_portfolio_consultation,
    calculate_coverage_total,
    find_coverages,
    find_overlapping_coverages,
    get_claim_channels,
    list_policies,
    retrieve_policy_terms,
    search_official_web,
)
from app.modules.qa.agent_validation import required_first_tool, validated_agent_response
from app.modules.qa.context import QaContext
from app.modules.qa.resolvers import OfficialAnswerer
from app.modules.qa.schemas import PortfolioQuestionResponse
from app.modules.qa.web_search import (
    OfficialWebSearcher,
    default_official_web_search,
)

type _QueuedAgentStreamItem = QaAgentStreamItem | BaseException | None


def build_qa_agent_runner(
    *,
    complete: JsonCompleter | None = None,
    official_answer: OfficialAnswerer | None = None,
    web_search: OfficialWebSearcher = default_official_web_search,
    model: str | None = None,
) -> QaAgentRunner:
    return OpenAiQaAgentRunner(
        complete=complete,
        official_answer=official_answer,
        web_search=web_search,
        model=model,
    )


class OpenAiQaAgentRunner:
    """Run a single OpenAI Agent that can call local QA tools."""

    def __init__(
        self,
        *,
        complete: JsonCompleter | None = None,
        official_answer: OfficialAnswerer | None = None,
        web_search: OfficialWebSearcher = default_official_web_search,
        model: str | None = None,
    ) -> None:
        self._complete = complete
        self._official_answer = official_answer
        self._web_search = web_search
        self._model = model

    def run(self, context: QaContext) -> PortfolioQuestionResponse:
        settings = get_settings()
        if not settings.openai_api_key:
            raise QaAgentUnavailable("OPENAI_API_KEY is not configured")

        dependencies = self._dependencies(context)
        result = Runner.run_sync(
            _agent(
                self._model or settings.openai_model,
                required_first_tool=required_first_tool(context),
            ),
            input=build_agent_input(context),
            context=dependencies,
            max_turns=5,
            run_config=RunConfig(
                model_provider=OpenAIProvider(api_key=settings.openai_api_key),
                tracing_disabled=True,
                trace_include_sensitive_data=False,
                workflow_name="Coverly grounded QA",
            ),
        )
        draft = result.final_output_as(AgentCounselorDraft, raise_if_incorrect_type=True)
        return _validated_or_cached_response(context, draft, dependencies)

    def stream(self, context: QaContext) -> Iterator[QaAgentStreamItem]:
        settings = get_settings()
        if not settings.openai_api_key:
            raise QaAgentUnavailable("OPENAI_API_KEY is not configured")

        dependencies = self._dependencies(context)
        queue: Queue[_QueuedAgentStreamItem] = Queue()
        worker = Thread(
            target=_run_streamed_worker,
            args=(
                context,
                dependencies,
                self._model or settings.openai_model,
                settings.openai_api_key,
                queue,
            ),
            daemon=True,
        )
        worker.start()
        while True:
            item = queue.get()
            if item is None:
                break
            if isinstance(item, BaseException):
                raise item
            yield item

    def _dependencies(self, context: QaContext) -> QaAgentDependencies:
        return QaAgentDependencies(
            context=context,
            complete=self._complete,
            official_answer=self._official_answer,
            web_search=self._web_search,
        )


def _agent(
    model: str,
    *,
    required_first_tool: str | None = None,
) -> Agent[QaAgentDependencies]:
    return Agent[QaAgentDependencies](
        name="Coverly Q&A Agent",
        model=model,
        instructions=_agent_instructions(),
        tools=[
            list_policies,
            find_coverages,
            calculate_coverage_total,
            find_overlapping_coverages,
            get_claim_channels,
            retrieve_policy_terms,
            answer_from_grounded_qa_tools,
            answer_from_portfolio_consultation,
            search_official_web,
        ],
        output_type=AgentCounselorDraft,
        output_guardrails=[grounded_output_guardrail],
        model_settings=ModelSettings(
            tool_choice=required_first_tool,
            parallel_tool_calls=False,
        ),
    )


@output_guardrail(name="coverly_grounded_output")
def grounded_output_guardrail(
    ctx: RunContextWrapper[QaAgentDependencies],
    _agent: Agent[QaAgentDependencies],
    output: AgentCounselorDraft,
) -> GuardrailFunctionOutput:
    try:
        ctx.context.validated_response = validated_agent_response(
            ctx.context.context,
            output,
            ctx.context,
        )
    except QaAgentUnavailable as exc:
        return GuardrailFunctionOutput(
            output_info={"valid": False, "reason": str(exc)},
            tripwire_triggered=True,
        )
    return GuardrailFunctionOutput(
        output_info={"valid": True},
        tripwire_triggered=False,
    )


def _run_streamed_worker(
    context: QaContext,
    dependencies: QaAgentDependencies,
    model: str,
    api_key: str,
    queue: Queue[_QueuedAgentStreamItem],
) -> None:
    try:
        asyncio.run(_run_streamed_agent(context, dependencies, model, api_key, queue))
    except Exception as exc:
        queue.put(exc)
    finally:
        queue.put(None)


async def _run_streamed_agent(
    context: QaContext,
    dependencies: QaAgentDependencies,
    model: str,
    api_key: str,
    queue: Queue[_QueuedAgentStreamItem],
) -> None:
    result = Runner.run_streamed(
        _agent(
            model,
            required_first_tool=required_first_tool(context),
        ),
        input=build_agent_input(context),
        context=dependencies,
        max_turns=5,
        hooks=_ProgressHooks(queue),
        run_config=RunConfig(
            model_provider=OpenAIProvider(api_key=api_key),
            tracing_disabled=True,
            trace_include_sensitive_data=False,
            workflow_name="Coverly grounded QA",
        ),
    )
    async for _event in result.stream_events():
        pass
    draft = result.final_output_as(AgentCounselorDraft, raise_if_incorrect_type=True)
    queue.put(QaAgentCompleted(_validated_or_cached_response(context, draft, dependencies)))


def _validated_or_cached_response(
    context: QaContext,
    draft: AgentCounselorDraft,
    dependencies: QaAgentDependencies,
) -> PortfolioQuestionResponse:
    if dependencies.validated_response is not None:
        return dependencies.validated_response
    dependencies.validated_response = validated_agent_response(context, draft, dependencies)
    return dependencies.validated_response


class _ProgressHooks(RunHooks[QaAgentDependencies]):
    def __init__(self, queue: Queue[_QueuedAgentStreamItem]) -> None:
        self._queue = queue
        self._emitted: set[str] = set()

    async def on_agent_start(self, _context: Any, _agent: Any) -> None:
        self._emit("routing", "질문에 맞는 확인 경로를 고르고 있어요.")

    async def on_tool_start(self, _context: Any, _agent: Any, tool: Any) -> None:
        tool_name = str(getattr(tool, "name", ""))
        stage, text = _tool_progress(tool_name)
        self._emit(stage, text)

    async def on_agent_end(self, _context: Any, _agent: Any, _output: Any) -> None:
        self._emit("validating", "확인한 근거와 답변을 검토하고 있어요.")

    def _emit(self, stage: str, text: str) -> None:
        if stage in self._emitted:
            return
        self._emitted.add(stage)
        self._queue.put(QaAgentProgress(stage=stage, text=text))


def _tool_progress(tool_name: str) -> tuple[str, str]:
    if tool_name == "search_official_web":
        return "official_web", "공식 자료에서 최신 정보를 확인하고 있어요."
    if tool_name == "retrieve_policy_terms":
        return "policy_terms", "증권 원문과 약관 근거를 찾고 있어요."
    if tool_name == "get_claim_channels":
        return "claim_channels", "청구에 필요한 보험사 안내를 확인하고 있어요."
    if tool_name in {
        "list_policies",
        "find_coverages",
        "calculate_coverage_total",
        "find_overlapping_coverages",
    }:
        return "portfolio_facts", "올려주신 증권의 가입 담보를 확인하고 있어요."
    return "grounding", "확인한 근거로 답변을 정리하고 있어요."


def build_agent_input(context: QaContext) -> str:
    history = "\n".join(
        f"{'사용자' if message.role == 'user' else '상담사'}: {message.content}"
        for message in context.history[-12:]
    )
    conversation = f"\n\n이전 대화:\n{history}" if history else ""
    prompt = (
        "사용자 질문에 답하세요.\n"
        f"지금 답할 질문: {context.question}{conversation}\n\n"
        "최신·현재 안내나 최근 변경을 묻는 질문이면 search_official_web을 먼저 호출하세요. "
        "법·제도 변경은 law_update, 보험사 안내는 insurer_guidance, 공개 약관은 "
        "public_policy_reference, 용어 설명은 insurance_term purpose를 사용하세요. "
        "사용자의 업로드 증권 질문은 아래 구조화 도구 중 필요한 것을 직접 고르세요: "
        "list_policies, find_coverages, calculate_coverage_total, find_overlapping_coverages, "
        "get_claim_channels, retrieve_policy_terms. "
        "어떤 구조화 도구도 맞지 않으면 answer_from_grounded_qa_tools를 호출하고, "
        "그래도 matched=false이면 사용자 증권의 비교·분석·상담은 "
        "answer_from_portfolio_consultation을 호출하세요. "
        "법, 제도, 보험 용어처럼 증권 밖의 사실을 묻는 질문은 search_official_web을 호출하세요. "
        "Coverly 사용법, 답변 범위, 개인정보 처리 방식, 왜 근거가 필요한지처럼 업로드 증권의 "
        "구체 사실이 필요 없는 질문은 answer_mode=general_guidance로 도구 없이 답할 수 있습니다. "
        "그 외에는 반드시 matched=true인 도구 결과 하나의 result_id를 선택해 최종 출력에 넣으세요."
    )
    return mask_demographic_identifiers(prompt)


def _agent_instructions() -> str:
    return """당신은 사용자의 편에서 업로드된 보험을 함께 살펴보는 보험 상담사입니다.

원칙:
- 특정 상품 가입, 해지, 증액을 지시하지 않습니다.
- 보상 가능 여부, 면책, 지급액을 단정하지 않습니다.
- 도구가 제공한 근거 밖의 담보, 금액, 조건을 지어내지 않습니다.
- 모든 보험증권은 보험분류와 상관없이 확인 대상입니다.
- 공개/공식 자료는 일반 안내이고, 사용자가 업로드한 증권 근거보다 우선하지 않습니다.
- 웹검색은 허용 도메인 안에서만 보조 근거로 사용합니다.
- 웹검색 결과만으로 사용자의 실제 가입 약관 보장 여부를 확정하지 않습니다.
- 질문 의도 판단은 당신이 하고, 가입 목록·담보 검색·금액 합산·중복 확인·청구 채널·약관 조회는
  반드시 도구 결과로 확인합니다.
- 사용법, 상담 범위, 개인정보 처리 방식, 근거가 필요한 이유처럼 사용자의 보험 사실을 조회할
  필요가 없는 질문은 answer_mode=general_guidance로 짧게 답할 수 있습니다.
- general_guidance 답변에서는 보험사명, 상품명, 가입금액, 보유 담보, 지급 가능성, 최신 법령
  사실을 말하지 않습니다.

응답:
- AgentCounselorDraft JSON 스키마로만 답하세요.
- 도구를 쓴 답변은 answer_mode=tool_grounded로 두고, selected_result_id에는 실제로 호출해 받은
  matched=true 결과의 result_id만 넣으세요.
- 도구 없이 답하는 일반 안내는 answer_mode=general_guidance로 두고 selected_result_id와
  evidence_ids를 비워 두세요.
- 도구 응답과 evidence를 재료로 사용해 최종 answer를 직접 작성하세요.
- 질문에 먼저 답하고, 필요한 설명만 이어가세요. 근거 목록을 그대로 복사하거나 전부 나열하지 마세요.
- 기본 답변은 짧은 문단 두세 개로 끝내고, 사용자가 묻지 않은 항목까지 완전 탐색해 나열하지 마세요.
- evidence_ids에는 실제 답변에 사용한 evidence의 id만 넣으세요.
- 웹검색처럼 evidence가 없는 도구는 빈 배열로 둡니다.
- 친근한 해요체를 쓰되 과장된 공감, 상투적인 인사, "안심하세요" 같은 단정은 피하세요.
- 이전 대화에서 이미 확인한 내용은 반복하지 말고 지금 질문에 필요한 맥락만 이어가세요.
- 사용자의 가족관계, 자녀, 학교, 소득처럼 evidence에 없는 개인 상황을 추측하지 마세요.
- 겹치는 보장은 같은 담보가 여러 증권에서 확인되는지와 실손형 중복 가능성을 구분해 설명하세요.
- 겹치는 보장 질문에는 실제로 겹치는 항목부터 답하고, 겹치지 않는 전체 담보를 다시 나열하지 마세요.
- 겹치는 보장 답변에는 확인된 중복이 정액형인지 실손형인지 반드시 구분해 말하세요.
- 가입금액 합계와 각 증권별 구성금액을 구분하세요. 합계를 각 증권이 각각 가진 금액처럼 쓰지 마세요.
- 정액형 담보가 겹치면 보험사·상품별 구성금액을 말하세요.
- 정액형 중복을 불필요하다고 단정하지 말고 약관별 지급 조건 확인 필요를 짧게 설명하세요.
- 서로 다른 질병 담보라는 이유만으로 "겹침이 없다"고 결론내리지 마세요.
- 법·제도·용어 질문에는 사용자 증권 담보를 억지로 연결하지 마세요.
- 강점은 실제 담보명과 가입금액 근거로 설명하고, 위험 분산·완벽한 대비·어떤 상황에서도
  대응 가능하다는 일반적인 칭찬을 만들지 마세요.
- 강점 질문은 근거가 분명한 핵심 두세 개만 말하고, 사용자가 묻지 않은 공백이나 추가 가입
  제안을 덧붙이지 마세요. 가입금액은 지급 확정액이 아니므로 "지급됩니다", "보장받을 수
  있어요", "안심하세요"라고 표현하지 마세요.
- 사용자가 질병 진단이나 사고를 말하면 관련해 확인된 보유 담보와 가입금액부터 구체적으로 말하세요.
- 가입 사실·가입금액은 확정해서 말하고, 실제 지급 여부만 약관·진단서 확인이 필요하다고 구분하세요.
- 직전 대화의 진단에 이어 "내 보험으로 받을 수 있어?"라고 물으면 그 진단 맥락을 유지하세요.
"""
