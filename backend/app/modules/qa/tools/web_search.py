"""Restricted official web search for the QA agent."""

import asyncio
import logging
import re
from collections.abc import AsyncIterator, Awaitable
from contextlib import asynccontextmanager
from threading import BoundedSemaphore
from typing import Any, Literal, Protocol, cast
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.integrations.openai import search_official_web_async
from app.modules.qa.context import QaContext
from app.modules.qa.pii import mask_qa_pii
from app.modules.reference_data.claim_channels import channels_for
from app.rag.official.sources import load_sources

SearchPurpose = Literal[
    "insurer_guidance",
    "public_policy_reference",
    "law_update",
    "insurance_term",
]
logger = logging.getLogger(__name__)
_URL_PATTERN = re.compile(r"https?://[^\s)\]]+")
_GENERAL_LAW_DOMAINS = ("law.go.kr", "korea.kr", "molit.go.kr")
_MAX_CITED_SOURCES = 3
_WEB_SEARCH_CONCURRENCY = 4
_WEB_SEARCH_SLOT_POLL_SECONDS = 0.05
_web_search_slots = BoundedSemaphore(_WEB_SEARCH_CONCURRENCY)


class WebSearchResult(BaseModel):
    status: Literal["searched", "unavailable"]
    answer: str = ""
    allowed_domains: list[str] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)
    limitation: str | None = None


class OfficialWebSearcher(Protocol):
    def __call__(
        self,
        query: str,
        *,
        purpose: SearchPurpose,
        allowed_domains: list[str],
    ) -> WebSearchResult | Awaitable[WebSearchResult]: ...


def search_allowed_domains(context: QaContext, purpose: SearchPurpose) -> list[str]:
    domains: list[str] = []
    if purpose in {"public_policy_reference", "law_update", "insurance_term"}:
        domains.extend(_official_source_domains(purpose))
    if purpose in {"insurer_guidance", "public_policy_reference"}:
        domains.extend(_held_insurer_domains(context))
    return list(dict.fromkeys(_allowlist_domain(domain) for domain in domains if domain))


async def default_official_web_search(
    query: str,
    *,
    purpose: SearchPurpose,
    allowed_domains: list[str],
) -> WebSearchResult:
    settings = get_settings()
    if not settings.openai_api_key:
        return WebSearchResult(
            status="unavailable",
            allowed_domains=allowed_domains,
            limitation="OPENAI_API_KEY is not configured for web search.",
        )
    if not allowed_domains:
        return WebSearchResult(
            status="unavailable",
            limitation=f"No allowed domains are configured for {purpose}.",
        )

    safe_query = _search_prompt(sanitize_search_query(query), purpose)
    try:
        async with _web_search_slot():
            response = await search_official_web_async(
                api_key=settings.openai_api_key,
                model=settings.openai_web_search_model,
                query=safe_query,
                allowed_domains=allowed_domains,
            )
    except Exception as exc:
        logger.warning("Official web search failed with %s", type(exc).__name__)
        return WebSearchResult(
            status="unavailable",
            allowed_domains=allowed_domains,
            limitation="허용된 공식 웹사이트 검색 요청을 완료하지 못했어요.",
        )
    answer = str(getattr(response, "output_text", "") or "")
    source_urls = _validated_source_urls(cast(Any, response), allowed_domains)
    if _contains_unallowed_url(answer, allowed_domains):
        return WebSearchResult(
            status="unavailable",
            allowed_domains=allowed_domains,
            limitation="허용되지 않은 웹사이트가 결과에 포함되어 답변에서 제외했어요.",
        )
    return WebSearchResult(
        status="searched",
        answer=answer,
        allowed_domains=allowed_domains,
        source_urls=source_urls,
    )


@asynccontextmanager
async def _web_search_slot() -> AsyncIterator[None]:
    """Acquire a process-wide permit without binding it to one event loop."""

    acquired = False
    try:
        while not acquired:
            acquired = _web_search_slots.acquire(blocking=False)
            if not acquired:
                await asyncio.sleep(_WEB_SEARCH_SLOT_POLL_SECONDS)
        yield
    finally:
        if acquired:
            _web_search_slots.release()


def sanitize_search_query(query: str) -> str:
    return mask_qa_pii(" ".join(query.split()))


def _search_prompt(query: str, purpose: SearchPurpose) -> str:
    instructions = (
        "허용된 공식 웹사이트만 근거로 질문에 한국어로 짧게 답하세요. "
        "답변에 사용한 주장과 직접 관련된 공식 페이지를 인용하세요. "
        "공식 페이지에서 확인되지 않는 내용은 추측하지 말고 확인하지 못했다고 답하세요."
    )
    if purpose == "law_update":
        instructions += (
            " 질문에 법률의 별칭이 있다면, 공식 페이지 본문에 그 별칭이 직접 등장하고 "
            "정식 법률명과 연결되는 경우에만 설명하세요. 관련 없는 법률을 유추하지 마세요."
        )
    return f"{instructions}\n\n질문: {query}"


def _official_source_domains(purpose: SearchPurpose) -> list[str]:
    """Official publisher domains we trust for web search.

    Every registered source counts, including ones we do not index. rag_enabled
    decides whether a document joins the RAG corpus, not whether its publisher
    is an official authority -- dropping 금융위원회 from the allowlist because its
    one indexed document was retired would lose a primary source for law and
    policy questions.
    """

    domains = list(
        dict.fromkeys(
            domain
            for source in load_sources()
            if _source_matches_purpose(source.category, source.publisher, purpose)
            if source.source_url and (domain := _domain_from_url(source.source_url))
        )
    )
    if purpose == "law_update":
        domains.extend(_GENERAL_LAW_DOMAINS)
    return list(dict.fromkeys(domains))


def _source_matches_purpose(category: str, publisher: str, purpose: SearchPurpose) -> bool:
    if purpose != "law_update":
        return True
    return category in {"law", "standard_clause"} or publisher == "금융위원회"


def _held_insurer_domains(context: QaContext) -> list[str]:
    insurers = list(
        dict.fromkeys(
            policy.기본정보.보험사 for policy in context.policies if policy.기본정보.보험사
        )
    )
    if not insurers:
        return []
    try:
        channel_set = channels_for(
            insurers,
            include_medical_indemnity_service=False,
        )
    except Exception:
        return []

    domains: list[str] = []
    for insurer in channel_set.insurers:
        for url in (insurer.homepage, insurer.claim_link):
            if url and (domain := _domain_from_url(url)):
                domains.append(domain)
    return list(dict.fromkeys(domains))


def _validated_source_urls(response: Any, allowed_domains: list[str]) -> list[str]:
    urls: list[str] = []
    for url in _cited_source_urls(response):
        domain = _domain_from_url(url)
        if domain is not None and _domain_allowed(domain, allowed_domains):
            urls.append(url)
    return list(dict.fromkeys(urls))[:_MAX_CITED_SOURCES]


def _cited_source_urls(value: Any) -> list[str]:
    urls: list[str] = []
    for item in _walk(value):
        if not isinstance(item, dict):
            continue
        if item.get("type") != "url_citation":
            continue
        raw_url = item.get("url")
        if isinstance(raw_url, str):
            urls.append(raw_url)
    return urls


def _walk(value: Any) -> list[Any]:
    if isinstance(value, BaseModel):
        return _walk(value.model_dump(mode="json"))
    if isinstance(value, dict):
        items: list[Any] = [value]
        for child in value.values():
            items.extend(_walk(child))
        return items
    if isinstance(value, list):
        items = []
        for child in value:
            items.extend(_walk(child))
        return items
    return []


def _domain_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return None
    return parsed.hostname.lower()


def _domain_allowed(domain: str, allowed_domains: list[str]) -> bool:
    return any(domain == allowed or domain.endswith(f".{allowed}") for allowed in allowed_domains)


def _allowlist_domain(domain: str) -> str:
    return domain.removeprefix("www.")


def _contains_unallowed_url(text: str, allowed_domains: list[str]) -> bool:
    for url in _URL_PATTERN.findall(text):
        domain = _domain_from_url(url)
        if domain is None or not _domain_allowed(domain, allowed_domains):
            return True
    return False
