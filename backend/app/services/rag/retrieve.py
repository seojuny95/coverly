"""Small official-source retriever with explicit reranking."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

import pdfplumber
from pydantic import BaseModel, Field

from app.services.llm import JsonCompleter, structured_completer
from app.services.rag.chunking import RagChunk, build_chunks
from app.services.rag.official_sources import OfficialSource, rag_sources

_TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣]+")
_STOPWORDS = {
    "보험",
    "보험금",
    "약관",
    "관련",
    "경우",
    "무엇",
    "뭐야",
    "알려줘",
    "설명",
    "되나요",
    "받나요",
}
_PROFILE_TERMS: dict[str, tuple[str, ...]] = {
    "claim_check": (
        "지급사유",
        "보험금의 지급사유",
        "보상하지",
        "지급하지",
        "면책",
        "감액",
        "지급하지 아니",
        "대기기간",
        "진단확정",
    ),
    "term_explain": ("뜻", "정의", "용어", "설명"),
}
_EXCLUSION_TERMS = ("보상하지", "지급하지", "면책", "제외", "안 나", "못 받")


@dataclass(frozen=True)
class RetrievalHit:
    chunk: RagChunk
    score: float
    keyword_score: int
    rerank_score: float


class Reranker(Protocol):
    def rerank(
        self,
        query: str,
        candidates: list[RetrievalHit],
        *,
        profile: str,
    ) -> list[RetrievalHit]:
        """Return candidates sorted by final relevance."""


class LexicalReranker:
    """Deterministic reranker used in tests and as a model-reranker fallback."""

    def rerank(
        self, query: str, candidates: list[RetrievalHit], *, profile: str
    ) -> list[RetrievalHit]:
        return sorted(
            (
                _with_rerank_score(hit, _rerank_score(query, hit.chunk, profile))
                for hit in candidates
            ),
            key=lambda hit: (-hit.rerank_score, -hit.keyword_score, hit.chunk.source_id),
        )


class _RerankChoice(BaseModel):
    chunk_id: str


class _RerankDraft(BaseModel):
    ranked: list[_RerankChoice] = Field(default_factory=list, max_length=24)


class ModelReranker:
    """LLM reranker with deterministic lexical fallback."""

    def __init__(self, complete: JsonCompleter | None = None) -> None:
        self._complete = complete or structured_completer(_RerankDraft)
        self._fallback = LexicalReranker()

    def rerank(
        self, query: str, candidates: list[RetrievalHit], *, profile: str
    ) -> list[RetrievalHit]:
        lexical = self._fallback.rerank(query, candidates, profile=profile)
        if not lexical:
            return []
        try:
            raw = self._complete(
                _reranker_system_prompt(profile),
                _reranker_user_prompt(query, lexical),
            )
            draft = _RerankDraft.model_validate(raw)
        except Exception:
            return lexical

        by_id = {hit.chunk.id: hit for hit in lexical}
        ranked: list[RetrievalHit] = []
        for choice in draft.ranked:
            hit = by_id.get(choice.chunk_id)
            if hit is not None and hit not in ranked:
                ranked.append(hit)
        ranked.extend(hit for hit in lexical if hit not in ranked)
        return ranked


@lru_cache(maxsize=1)
def load_official_chunks() -> tuple[RagChunk, ...]:
    chunks: list[RagChunk] = []
    for source in rag_sources():
        if source.status != "downloaded" or source.absolute_path is None:
            continue
        if not source.absolute_path.exists():
            continue
        if source.absolute_path.suffix.casefold() == ".xml":
            chunks.extend(_load_law_xml_chunks(source))
        else:
            chunks.extend(_load_pdf_chunks(source))
    return tuple(chunks)


def retrieve(
    query: str,
    *,
    chunks: tuple[RagChunk, ...] | None = None,
    profile: str = "general",
    candidate_k: int = 24,
    final_k: int = 6,
    reranker: Reranker | None = None,
) -> list[RetrievalHit]:
    """Retrieve official-source chunks, then rerank and trim."""
    terms = _expanded_terms(query, profile)
    if not terms:
        return []

    candidates: list[RetrievalHit] = []
    corpus = chunks if chunks is not None else load_official_chunks()
    for chunk in corpus:
        keyword_score = _keyword_score(chunk, terms)
        if keyword_score <= 0:
            continue
        candidates.append(
            RetrievalHit(
                chunk=chunk,
                score=float(keyword_score),
                keyword_score=keyword_score,
                rerank_score=0.0,
            )
        )
    candidates.sort(key=lambda hit: (-hit.keyword_score, hit.chunk.source_id, hit.chunk.page_start))
    ranked = (reranker or LexicalReranker()).rerank(
        query,
        candidates[:candidate_k],
        profile=profile,
    )
    return ranked[:final_k]


def infer_profile(query: str) -> str:
    if any(term in query for term in ("보상", "보험금", "지급", "받을 수", "면책")):
        return "claim_check"
    if any(term in query for term in ("뜻", "뭐야", "무엇", "용어", "설명")):
        return "term_explain"
    return "general"


def _load_pdf_chunks(source: OfficialSource) -> list[RagChunk]:
    assert source.absolute_path is not None
    with pdfplumber.open(str(source.absolute_path)) as pdf:
        pages = [(page.extract_text() or "") for page in pdf.pages]
    return build_chunks(source, pages)


def _load_law_xml_chunks(source: OfficialSource) -> list[RagChunk]:
    assert source.absolute_path is not None
    root = ET.fromstring(source.absolute_path.read_text(encoding="utf-8"))
    chunks: list[RagChunk] = []
    for index, article in enumerate(root.findall(".//조문단위"), start=1):
        if article.findtext("조문여부") != "조문":
            continue
        number = (article.findtext("조문번호") or "").strip()
        title = (article.findtext("조문제목") or "").strip()
        body = _law_article_text(article)
        if len(body) < 30:
            continue
        label = f"제{number}조({title})" if title else f"제{number}조"
        chunks.append(
            RagChunk(
                id=f"{source.id}:{number or index}",
                source_id=source.id,
                source_title=source.title,
                source_category=source.category,
                publisher=source.publisher,
                text=body,
                page_start=index,
                page_end=index,
                label=label,
                citation_label=f"{source.title} {label}",
                version_label=source.version_label,
                source_url=source.source_url,
                local_path=source.local_path,
            )
        )
    return chunks


def _law_article_text(article: ET.Element) -> str:
    values: list[str] = []
    for tag in ("조문내용", "조문참고자료"):
        text = article.findtext(tag)
        if text and text.strip():
            values.append(" ".join(text.split()))
    for element in (
        article.findall(".//항내용") + article.findall(".//호내용") + article.findall(".//목내용")
    ):
        if element.text and element.text.strip():
            values.append(" ".join(element.text.split()))
    return "\n".join(dict.fromkeys(values))


def _expanded_terms(query: str, profile: str) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for token in _TOKEN_RE.findall(query):
        for term in _term_variants(token):
            if len(term) < 2 or term in _STOPWORDS or term in seen:
                continue
            seen.add(term)
            terms.append(term)
    for term in _PROFILE_TERMS.get(profile, ()):
        if term not in seen:
            seen.add(term)
            terms.append(term)
    if any(term in query for term in ("쉽게", "바꾸", "개선", "이해")):
        for term in ("용어순화", "소비자", "이해도", "개선"):
            if term not in seen:
                seen.add(term)
                terms.append(term)
    return terms[:16]


def _term_variants(token: str) -> tuple[str, ...]:
    variants = [token]
    for suffix in ("에서는", "에서", "으로", "라는", "은", "는", "이", "가", "을", "를"):
        if token.endswith(suffix) and len(token) > len(suffix) + 1:
            variants.append(token[: -len(suffix)])
            break
    return tuple(dict.fromkeys(variants))


def _keyword_score(chunk: RagChunk, terms: list[str]) -> int:
    title = (chunk.label or "").casefold()
    text = chunk.text.casefold()
    counts: Counter[str] = Counter()
    for term in terms:
        folded = term.casefold()
        title_count = title.count(folded)
        text_count = text.count(folded)
        if title_count or text_count:
            counts[term] = title_count * 4 + text_count
    if not counts:
        return 0
    return sum(counts.values()) + len(counts) * 3


def _rerank_score(query: str, chunk: RagChunk, profile: str) -> float:
    terms = _expanded_terms(query, profile)
    score = float(_keyword_score(chunk, terms))
    label = chunk.label or ""
    if profile == "claim_check":
        if any(term in chunk.text for term in ("보험금의 지급사유", "지급사유")):
            score += 6
        if any(term in label or term in chunk.text for term in _EXCLUSION_TERMS):
            score += 5
        if (
            chunk.source_category == "law"
            and any(term in query for term in ("설명", "사유"))
            and any(term in chunk.text for term in ("감액하여", "지급하지 아니", "설명하여야"))
        ):
            score += 25
    if profile == "term_explain" and label and any(term in label for term in terms):
        score += 4
    if chunk.source_category == "standard_clause":
        score += 1
    return score


def _with_rerank_score(hit: RetrievalHit, rerank_score: float) -> RetrievalHit:
    return RetrievalHit(
        chunk=hit.chunk,
        score=hit.score,
        keyword_score=hit.keyword_score,
        rerank_score=rerank_score,
    )


def _reranker_system_prompt(profile: str) -> str:
    return (
        "제공된 공식자료 후보를 질문 관련성이 높은 순서로 정렬하세요. "
        "근거가 직접적인 조문·약관 발췌문을 우선하세요. "
        f"검색 프로필: {profile}. chunk_id만 반환하세요."
    )


def _reranker_user_prompt(query: str, candidates: list[RetrievalHit]) -> str:
    payload = {
        "query": query,
        "candidates": [
            {
                "chunk_id": hit.chunk.id,
                "source_title": hit.chunk.source_title,
                "label": hit.chunk.label,
                "text": hit.chunk.text[:700],
            }
            for hit in candidates
        ],
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
