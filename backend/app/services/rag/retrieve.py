"""Small official-source retriever with explicit reranking."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

import pdfplumber

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


@lru_cache(maxsize=1)
def load_official_chunks() -> tuple[RagChunk, ...]:
    chunks: list[RagChunk] = []
    for source in rag_sources():
        if source.status != "downloaded" or source.absolute_path is None:
            continue
        if not source.absolute_path.exists():
            continue
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


def _expanded_terms(query: str, profile: str) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for token in _TOKEN_RE.findall(query):
        if len(token) < 2 or token in _STOPWORDS or token in seen:
            continue
        seen.add(token)
        terms.append(token)
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
