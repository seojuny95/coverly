"""Resolve the grounded tool result shared by review and final validation."""

from app.modules.qa.agent.contracts import QaAgentDependencies, RegisteredToolResult


def select_tool_result(
    dependencies: QaAgentDependencies,
    result_id: str | None,
) -> RegisteredToolResult | None:
    """Return the only result that can safely ground the agent draft."""

    selected = dependencies.tool_results.get(result_id) if result_id is not None else None
    if _requires_web_result(dependencies):
        if selected is not None and selected.kind == "web":
            return selected
        web_results = [item for item in dependencies.tool_results.values() if item.kind == "web"]
        return web_results[0] if len(web_results) == 1 else None

    if selected is not None:
        return selected

    results = list(dependencies.tool_results.values())
    if len(results) == 1:
        return results[0]
    if results and all(item.response == results[0].response for item in results[1:]):
        return results[0]
    return None


def _requires_web_result(dependencies: QaAgentDependencies) -> bool:
    decision = dependencies.input_decision
    return decision is not None and decision.requires_fresh_official_source
