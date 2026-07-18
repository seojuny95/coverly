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
from app.modules.qa.agent.output_review import classify_output_safety
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
    try:
        safety = classify_output_safety(ctx.context, output)
    except Exception as exc:
        return GuardrailFunctionOutput(
            output_info={
                "valid": False,
                "reason": "output_review_unavailable",
                "error_type": type(exc).__name__,
            },
            tripwire_triggered=True,
        )
    if not safety.is_safe:
        return GuardrailFunctionOutput(
            output_info=safety.model_dump(mode="json"),
            tripwire_triggered=True,
        )
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
