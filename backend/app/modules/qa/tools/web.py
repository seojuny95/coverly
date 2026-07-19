"""Restricted official-web Agent SDK tool and response mapping."""

import inspect
from urllib.parse import urlparse

from agents import RunContextWrapper, function_tool

from app.modules.qa.agent.contracts import GroundedToolAnswer, QaAgentDependencies
from app.modules.qa.schemas import AnswerCitation, PortfolioQuestionResponse
from app.modules.qa.tools.web_search import (
    SearchPurpose,
    WebSearchResult,
    sanitize_search_query,
    search_allowed_domains,
)


@function_tool
async def search_official_web(
    wrapper: RunContextWrapper[QaAgentDependencies],
    purpose: SearchPurpose,
) -> GroundedToolAnswer:
    """Search current information only on approved official or held-insurer domains.

    Args:
        purpose: The official-source category that controls the domain allowlist.
    """

    context = wrapper.context.context
    allowed_domains = search_allowed_domains(context, purpose)
    search_result = wrapper.context.web_search(
        sanitize_search_query(context.question),
        purpose=purpose,
        allowed_domains=allowed_domains,
    )
    result = await search_result if inspect.isawaitable(search_result) else search_result
    response = web_search_response(result)
    return wrapper.context.register(
        "web",
        response,
        trust_level="generated" if response.status == "answered" else "deterministic",
    )


def web_search_response(result: WebSearchResult) -> PortfolioQuestionResponse:
    if result.status != "searched" or not result.answer.strip() or not result.source_urls:
        limitation = result.limitation or "허용된 공식 웹사이트에서 근거를 확인하지 못했어요."
        return PortfolioQuestionResponse(
            status="no_data",
            answer=(
                "최신 공식 안내를 확인하지 못했어요. 허용된 공식 웹사이트에서 "
                "출처가 확인되는 결과를 찾지 못했습니다."
            ),
            citations=[],
            limitations=[limitation],
            suggestions=[],
        )

    citations = [
        AnswerCitation(
            policy_id=None,
            insurer=None,
            product_name=None,
            source_id=url,
            source_title=urlparse(url).hostname,
            source_category="official_web",
            source_url=url,
        )
        for url in result.source_urls
    ]
    return PortfolioQuestionResponse(
        status="answered",
        answer=f"최신 공식 안내를 찾아봤어요.\n\n{result.answer.strip()}",
        citations=citations,
        limitations=["공개된 공식 웹사이트에서 확인한 현재 안내예요."],
        suggestions=[],
        generation="llm",
    )
