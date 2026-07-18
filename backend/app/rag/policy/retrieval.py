"""Retrieve uploaded-policy chunks within explicit session boundaries."""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Callable

from app.integrations.postgres.policy_rag_store import shared_policy_store
from app.rag.embeddings import Embedder, openai_embedder_from_settings
from app.rag.policy.models import PolicyRetrievalHit
from app.rag.policy.session_tokens import verified_policy_session_ids
from app.rag.policy.store import PolicyRagStore
from app.rag.text import normalize_text

_TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣]+")
_RRF_K = 20


def retrieve_policy_context(
    session_tokens: list[str],
    query: str,
    *,
    top_k: int = 4,
    candidate_k: int = 48,
    store: PolicyRagStore | None = None,
    embedder: Embedder | None = None,
) -> list[PolicyRetrievalHit]:
    if not session_tokens:
        return []
    session_ids = verified_policy_session_ids(session_tokens)
    return retrieve_policy_context_by_session_ids(
        session_ids,
        query,
        top_k=top_k,
        candidate_k=candidate_k,
        store=store,
        embedder=embedder,
    )


def retrieve_policy_context_by_session_ids(
    session_ids: list[str],
    query: str,
    *,
    top_k: int = 4,
    candidate_k: int = 48,
    store: PolicyRagStore | None = None,
    embedder: Embedder | None = None,
) -> list[PolicyRetrievalHit]:
    """Retrieve with server-resolved document ids, never client-supplied ids."""

    normalized = _normalize_query(query)
    if not session_ids or not normalized or top_k <= 0:
        return []
    active_embedder = embedder or openai_embedder_from_settings()
    query_embedding = active_embedder.embed_texts([normalized])[0]
    hits = (store or shared_policy_store()).query(
        session_ids,
        query_embedding,
        top_k=max(top_k, candidate_k),
    )
    deduped = _dedupe_hits(hits)
    return _rerank_with_rrf(normalized, deduped)[:top_k]


def _normalize_query(query: str) -> str:
    return " ".join(query.split())


def _dedupe_hits(hits: list[PolicyRetrievalHit]) -> list[PolicyRetrievalHit]:
    deduped: list[PolicyRetrievalHit] = []
    seen: set[str] = set()
    for hit in hits:
        key = normalize_text(hit.chunk.text)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(hit)
    return deduped


def _rerank_with_rrf(query: str, hits: list[PolicyRetrievalHit]) -> list[PolicyRetrievalHit]:
    if not hits:
        return []

    terms = _query_terms(query)
    keyword_scores = _bm25_scores(hits, terms)
    vector_ranks = _rank_positions(
        hits,
        key=lambda hit: (-hit.score, hit.chunk.session_id, hit.chunk.chunk_index, hit.chunk.id),
    )
    keyword_ranks = _rank_positions(
        hits,
        key=lambda hit: (
            -keyword_scores[hit.chunk.id],
            -hit.score,
            hit.chunk.session_id,
            hit.chunk.chunk_index,
            hit.chunk.id,
        ),
    )

    ranked = sorted(
        hits,
        key=lambda hit: (
            -_rrf_score(vector_ranks[hit.chunk.id], keyword_ranks[hit.chunk.id]),
            -keyword_scores[hit.chunk.id],
            -hit.score,
            hit.chunk.session_id,
            hit.chunk.chunk_index,
            hit.chunk.id,
        ),
    )
    return [
        PolicyRetrievalHit(
            chunk=hit.chunk,
            score=_rrf_score(vector_ranks[hit.chunk.id], keyword_ranks[hit.chunk.id]),
        )
        for hit in ranked
    ]


def _rank_positions(
    hits: list[PolicyRetrievalHit],
    *,
    key: Callable[[PolicyRetrievalHit], tuple[float | int | str, ...]],
) -> dict[str, int]:
    ordered = sorted(hits, key=key)
    return {hit.chunk.id: rank for rank, hit in enumerate(ordered, start=1)}


def _rrf_score(*ranks: int, k: int = _RRF_K) -> float:
    return sum(1 / (k + rank) for rank in ranks)


def _bm25_scores(
    hits: list[PolicyRetrievalHit],
    terms: tuple[str, ...],
) -> dict[str, float]:
    documents = {hit.chunk.id: _tokens(hit.chunk.text) for hit in hits}
    doc_count = len(documents)
    avgdl = sum(len(tokens) for tokens in documents.values()) / doc_count if doc_count else 0.0
    doc_freqs: Counter[str] = Counter()
    for tokens in documents.values():
        doc_freqs.update(set(tokens))

    return {
        hit.chunk.id: _bm25_score(
            documents[hit.chunk.id],
            terms,
            doc_count=doc_count,
            avgdl=avgdl,
            doc_freqs=doc_freqs,
        )
        for hit in hits
    }


def _bm25_score(
    document_tokens: tuple[str, ...],
    query_terms: tuple[str, ...],
    *,
    doc_count: int,
    avgdl: float,
    doc_freqs: Counter[str],
) -> float:
    if not document_tokens or not query_terms or doc_count == 0 or avgdl == 0:
        return 0.0

    counts = Counter(document_tokens)
    score = 0.0
    k1 = 1.2
    b = 0.75
    for term in query_terms:
        term_freq = counts[term.casefold()]
        if term_freq <= 0:
            continue
        doc_freq = doc_freqs.get(term.casefold(), 0)
        idf = math.log(1 + (doc_count - doc_freq + 0.5) / (doc_freq + 0.5))
        numerator = term_freq * (k1 + 1)
        denominator = term_freq + k1 * (1 - b + b * len(document_tokens) / avgdl)
        score += idf * numerator / denominator
    return score


def _tokens(text: str) -> tuple[str, ...]:
    tokens = [token.casefold() for token in _TOKEN_RE.findall(text) if token.strip()]
    for token in tuple(tokens):
        if any("가" <= char <= "힣" for char in token):
            tokens.extend(_char_ngrams(token))
    return tuple(dict.fromkeys(tokens))


def _query_terms(query: str) -> tuple[str, ...]:
    return _tokens(" ".join((query, _query_expansions(query))))


def _query_expansions(query: str) -> str:
    normalized = " ".join(query.split())
    compact = normalized.replace(" ", "")
    expansions: list[str] = []

    for trigger, terms in (
        ("차값", "차량가액 차량 자동차보험"),
        ("차량 평가 금액", "차량가액"),
        ("평가 금액", "차량가액"),
        ("차를 대상", "자동차보험 차량"),
        ("심장질환", "심질환 허혈성심질환"),
        ("뇌혈관 질환", "뇌혈관질환"),
        ("월 보험료", "1회 보험료 월납"),
        ("매달", "월납 보험료 1회 보험료"),
        ("몇 년 동안", "계약사항 납입기간 납입주기 월납"),
        ("내는 계약", "계약사항 납입기간 납입주기 월납"),
        ("유사암 제외", "유사암제외"),
        ("사고 처리지원금", "교통사고처리지원금 처리지원금"),
        ("자가용 운전자", "자가용운전자"),
        ("부상치료비", "자동차부상치료비"),
    ):
        if trigger in normalized or trigger.replace(" ", "") in compact:
            expansions.append(terms)

    expansions.extend(_amount_expansions(normalized))
    return " ".join(expansions)


def _amount_expansions(query: str) -> tuple[str, ...]:
    expansions: list[str] = []
    for match in re.finditer(r"(\d+)\s*억원", query):
        amount_in_manwon = int(match.group(1)) * 10000
        expansions.append(f"{amount_in_manwon:,}만원")
        expansions.append(f"{amount_in_manwon:,} 만원")
        expansions.append(f"{amount_in_manwon}만원")
    for match in re.finditer(r"(\d+)\s*천만원", query):
        amount_in_manwon = int(match.group(1)) * 1000
        expansions.append(f"{amount_in_manwon:,}만원")
        expansions.append(f"{amount_in_manwon:,} 만원")
        expansions.append(f"{amount_in_manwon}만원")
    for match in re.finditer(r"(\d+)\s*만원대", query):
        base = int(match.group(1)) * 10000
        expansions.extend(f"{amount:,}원" for amount in range(base, base + 10000, 1000))
    return tuple(expansions)


def _char_ngrams(text: str) -> tuple[str, ...]:
    if len(text) < 2:
        return ()
    ngrams: list[str] = []
    for size in (2, 3, 4):
        if len(text) < size:
            continue
        ngrams.extend(text[index : index + size] for index in range(len(text) - size + 1))
    return tuple(ngrams)
