"""OpenAI Agents SDK definition for grounded insurance counseling."""

from agents import (
    Agent,
    GuardrailFunctionOutput,
    ModelSettings,
    RunContextWrapper,
    output_guardrail,
)

from app.modules.qa.agent.contracts import (
    AgentCounselorDraft,
    QaAgentDependencies,
    QaAgentUnavailable,
)
from app.modules.qa.agent.input_guardrail import qa_input_guardrail
from app.modules.qa.agent.prompt import agent_instructions
from app.modules.qa.agent.validation import validated_agent_response
from app.modules.qa.tools.registry import QA_AGENT_TOOLS


def create_qa_agent(model: str) -> Agent[QaAgentDependencies]:
    return Agent[QaAgentDependencies](
        name="Coverly Q&A Agent",
        model=model,
        instructions=lambda ctx, _agent: agent_instructions(ctx.context.input_decision),
        tools=QA_AGENT_TOOLS,
        input_guardrails=[qa_input_guardrail],
        output_guardrails=[grounded_output_guardrail],
        output_type=AgentCounselorDraft,
        model_settings=ModelSettings(parallel_tool_calls=False),
    )


@output_guardrail(name="coverly_grounded_output")
def grounded_output_guardrail(
    ctx: RunContextWrapper[QaAgentDependencies],
    _agent: Agent[QaAgentDependencies],
    output: AgentCounselorDraft,
) -> GuardrailFunctionOutput:
    """Validate the draft against its evidence and cache the validated response.

    Output safety now rests on the compose prompt (no-sales, placeholder-only,
    per-source attribution) plus deterministic numeric grounding inside
    ``validated_agent_response``; there is no separate output-safety LLM. This
    guardrail runs validation, caches the result for reuse, and trips only when
    validation cannot ground the draft (``QaAgentUnavailable``).
    """

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
    return GuardrailFunctionOutput(output_info={"valid": True}, tripwire_triggered=False)
