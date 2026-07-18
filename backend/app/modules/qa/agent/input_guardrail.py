"""SDK input guardrail for QA scope and freshness requirements."""

from agents import (
    Agent,
    GuardrailFunctionOutput,
    RunContextWrapper,
    TResponseInputItem,
    input_guardrail,
)

from app.core.config import get_settings
from app.integrations.openai.client import dump_prompt_json, structured_completer
from app.modules.qa.agent.contracts import QaAgentDependencies, QaInputDecision
from app.modules.qa.pii import mask_qa_pii


@input_guardrail(name="coverly_qa_input", run_in_parallel=False)
def qa_input_guardrail(
    ctx: RunContextWrapper[QaAgentDependencies],
    _agent: Agent[QaAgentDependencies],
    _input: str | list[TResponseInputItem],
) -> GuardrailFunctionOutput:
    dependencies = ctx.context
    completer = dependencies.classify_input or structured_completer(
        QaInputDecision,
        model=get_settings().openai_qa_guardrail_model,
    )
    raw = completer(_guardrail_instructions(), _guardrail_input(dependencies))
    decision = QaInputDecision.model_validate(raw)
    decision = decision.model_copy(update={"should_block": decision.scope == "out_of_scope"})
    dependencies.input_decision = decision
    return GuardrailFunctionOutput(
        output_info=decision.model_dump(mode="json"),
        tripwire_triggered=decision.should_block,
    )


def requires_fresh_official_source(dependencies: QaAgentDependencies) -> bool:
    decision = dependencies.input_decision
    return decision is not None and decision.requires_fresh_official_source


def requires_uploaded_policy_terms(dependencies: QaAgentDependencies) -> bool:
    decision = dependencies.input_decision
    return decision is not None and decision.requires_uploaded_policy_terms


def _guardrail_input(dependencies: QaAgentDependencies) -> str:
    context = dependencies.context
    payload = {
        "question": context.question,
        "history": [message.model_dump(mode="json") for message in context.history],
    }
    return mask_qa_pii(dump_prompt_json(payload))


def _guardrail_instructions() -> str:
    return """사용자 입력의 범위와 필요한 근거 종류만 분류하세요.

- insurance: 보험, 가입 증권, 담보, 약관, 청구, 보험 제도나 보험 용어에 관한 질문
- coverly: Coverly의 기능, 답변 범위, 개인정보 사용, 근거 정책에 관한 질문
- greeting: 짧은 인사나 감사
- mixed: 보험 범위 질문과 범위 밖 질문이 함께 있는 경우
- out_of_scope: 위 범위와 관계없는 질문만 있는 경우
- 질문에 답할 수 있는 보험 부분이 하나라도 있고 범위 밖 요청도 함께 있으면 반드시 mixed입니다.
  범위 밖 부분이 포함됐다는 이유만으로 전체를 out_of_scope로 분류하지 마세요.
- should_block은 out_of_scope일 때만 true입니다. greeting과 mixed는 false입니다.
- insurance_request에는 보험 상담 범위에서 실제로 답해야 할 요청만 독립된 문장으로 씁니다.
- out_of_scope_request에는 답하지 않아야 할 범위 밖 요청만 씁니다.
- mixed에서는 두 request가 모두 있어야 합니다. insurance에서는 insurance_request만,
  out_of_scope에서는 out_of_scope_request만 둡니다.
- greeting은 "안녕하세요", "고마워요"처럼 정보 요청이 없는 사회적 표현만 해당합니다.
- 날씨, 주가, 맛집처럼 보험과 무관한 정보를 요청하면 greeting이 아니라 out_of_scope이며
  should_block=true입니다.
- 예: "보험료를 확인하고 내일 날씨도 알려줘"는 mixed, should_block=false입니다.
- 예: "내일 날씨를 알려줘"는 out_of_scope, should_block=true입니다.
- requires_fresh_official_source는 사용자가 현재 상태, 최근 변경, 최신 공지처럼 시점에 따라
  달라질 수 있는 공식 사실을 요구할 때만 true로 두세요.
- requires_uploaded_policy_terms는 사용자가 자신이 가입한 보험의 정확한 지급 조건, 면책,
  대기기간, 보장개시일처럼 실제 계약 원문 없이는 확정할 수 없는 내용을 물을 때 true입니다.
- 일반적인 보험 용어·표준 제도 설명은 requires_uploaded_policy_terms=false입니다.
- 단순 용어 설명, 업로드 증권 사실, 가입금액, 담보 목록은 false입니다.
- 키워드 존재만으로 정하지 말고 문장 전체 의미와 이전 대화 맥락으로 판단하세요.
- 보험 사실을 답하거나 추측하지 말고 분류 결과만 반환하세요."""
