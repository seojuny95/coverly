from app.modules.qa.agent.contracts import QaAgentDependencies, QaInputDecision
from app.modules.qa.agent.selection import select_tool_result
from app.modules.qa.context import build_qa_context
from app.modules.qa.schemas import PortfolioQuestionResponse
from app.modules.qa.tools.web_search import WebSearchResult


def _unused_web_search(*_args: object, **_kwargs: object) -> WebSearchResult:
    return WebSearchResult(status="unavailable")


def _dependencies(*, requires_web: bool = False) -> QaAgentDependencies:
    dependencies = QaAgentDependencies(
        context=build_qa_context("질문", [], None, []),
        complete=None,
        official_answer=None,
        web_search=_unused_web_search,
    )
    dependencies.input_decision = QaInputDecision(
        scope="insurance",
        should_block=False,
        requires_fresh_official_source=requires_web,
        insurance_request="질문",
        out_of_scope_request=None,
        reason="테스트",
    )
    return dependencies


def _response(answer: str) -> PortfolioQuestionResponse:
    return PortfolioQuestionResponse(
        status="answered",
        answer=answer,
        citations=[],
        limitations=[],
    )


def test_selects_an_explicit_registered_result() -> None:
    dependencies = _dependencies()
    registered = dependencies.register("consultation", _response("선택된 답변"))
    dependencies.register("official_rag", _response("다른 답변"))

    selected = select_tool_result(dependencies, registered.result_id)

    assert selected is not None
    assert selected.response.answer == "선택된 답변"


def test_recovers_a_single_result_without_an_explicit_selection() -> None:
    dependencies = _dependencies()
    dependencies.register("consultation", _response("유일한 답변"))

    selected = select_tool_result(dependencies, None)

    assert selected is not None
    assert selected.response.answer == "유일한 답변"


def test_accepts_multiple_results_only_when_their_responses_are_equal() -> None:
    dependencies = _dependencies()
    shared_response = _response("같은 답변")
    dependencies.register("consultation", shared_response)
    dependencies.register("official_rag", shared_response.model_copy())

    selected = select_tool_result(dependencies, None)

    assert selected is not None
    assert selected.response == shared_response


def test_rejects_ambiguous_results_with_different_responses() -> None:
    dependencies = _dependencies()
    dependencies.register("consultation", _response("첫 답변"))
    dependencies.register("official_rag", _response("둘째 답변"))

    assert select_tool_result(dependencies, None) is None


def test_fresh_information_uses_the_only_web_result_over_an_explicit_non_web_result() -> None:
    dependencies = _dependencies(requires_web=True)
    non_web = dependencies.register("official_rag", _response("기존 공식자료"))
    dependencies.register("web", _response("최신 공식 웹자료"))

    selected = select_tool_result(dependencies, non_web.result_id)

    assert selected is not None
    assert selected.kind == "web"
    assert selected.response.answer == "최신 공식 웹자료"


def test_fresh_information_rejects_multiple_web_results_without_selection() -> None:
    dependencies = _dependencies(requires_web=True)
    dependencies.register("web", _response("첫 웹 결과"))
    dependencies.register("web", _response("둘째 웹 결과"))

    assert select_tool_result(dependencies, None) is None
