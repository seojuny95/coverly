"""Compose prompt and streaming answer function for the grounded QA agent.

The compose step turns a validated ``GroundedAnswerSpec`` into streamed answer
prose. The critical safety rule is enforced entirely through the prompt: the
model must write every amount as a ``{{label}}`` placeholder and never a raw
digit, so the downstream sentence-verify stage (``compose_stream.py``) can
substitute and re-verify each number before release. Sentence verification and
runtime wiring live elsewhere — this module only assembles prompts and yields
the raw token stream from the injected streamer.
"""

from collections.abc import Iterator

from app.integrations.openai.client import TextStreamer, stream_completion
from app.modules.qa.agent.answer_spec import GroundedAnswerSpec
from app.modules.qa.pii import mask_qa_pii

COMPOSE_SYSTEM = """당신은 사용자의 편에서 업로드된 보험을 함께 살펴보는 보험 상담사입니다.

톤:
- 모든 문장은 존댓말(해요체)로 씁니다.
- 짧은 문단 두세 개로 답하고, 근거 목록을 그대로 나열하지 않습니다.

금지:
- 특정 상품 가입, 해지, 증액, 추가 가입을 권유하지 않습니다.
- 손해나 위험을 과장해 행동을 압박하지 않습니다.
- 판매·가입 권유로 읽히는 표현을 쓰지 않습니다.

숫자 규칙(반드시 지킵니다):
- 금액과 숫자는 반드시 제공된 {{라벨}} 자리표시자로만 쓰고, 숫자를 직접 쓰지 마세요.
- 사용 가능한 자리표시자 목록에 없는 금액이나 숫자는 언급하지 않습니다.
- {{라벨}}은 그대로 답변 문장 안에 씁니다. 값으로 치환하지 않습니다.

귀속 규칙(반드시 지킵니다):
- 각 금액은 그 금액이 속한 담보·보험사에만 귀속시키고, 서로 다른 담보나 보험사의
  금액을 한 문장에서 섞어 쓰지 않습니다.
- 어떤 자리표시자가 어느 담보의 금액인지 확인되지 않으면 그 담보의 금액을 언급하지 않습니다.
- 합계가 필요하면 개별 금액과 구분해 '총 합계'임을 분명히 밝히고, 개별 담보의
  금액처럼 제시하지 않습니다.

근거 수준:
- mode가 grounded이면 제공된 사실만으로 확정된 내용을 설명합니다.
- mode가 general_guidance이면 일반적인 안내이며 실제 약관 확인이 필요하다는 점을 알립니다.
- 제공되지 않은 담보, 금액, 조건은 지어내지 않습니다."""


def build_compose_prompt(spec: GroundedAnswerSpec, question: str) -> tuple[str, str]:
    """Assemble (system, user) prompts for the compose stream. PII masked."""

    facts_block = "\n".join(f"- {fact}" for fact in spec.facts) or "- (제공된 사실 없음)"

    labels_block = (
        "\n".join(f"- {{{{{label}}}}} = {value}" for label, value in spec.amounts.items())
        or "- (사용 가능한 자리표시자 없음)"
    )

    user = (
        f"답변 근거 수준(mode): {spec.mode}\n\n"
        f"확인된 사실:\n{facts_block}\n\n"
        f"사용 가능한 자리표시자:\n{labels_block}\n\n"
        f"사용자 질문: {question}"
    )

    return COMPOSE_SYSTEM, mask_qa_pii(user)


def compose_answer_stream(
    spec: GroundedAnswerSpec,
    question: str,
    *,
    streamer: TextStreamer = stream_completion,
) -> Iterator[str]:
    """Assemble the compose prompt and yield raw tokens from ``streamer``."""

    system, user = build_compose_prompt(spec, question)
    yield from streamer(system, user)
