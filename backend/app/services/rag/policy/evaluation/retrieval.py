"""Retrieval evaluation for uploaded-policy RAG."""

from __future__ import annotations

import json
import os
import subprocess
import time
import unicodedata
import uuid
from argparse import ArgumentParser
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

from app.services.policy.models import ParsedDocument
from app.services.policy.parsing import parse_document
from app.services.rag.embeddings import Embedder, HashingEmbedder, openai_embedder_from_settings
from app.services.rag.policy.indexing import build_policy_vector_records
from app.services.rag.policy.models import PolicyRetrievalHit, PolicyVectorRecord
from app.services.rag.policy.retrieval import retrieve_policy_context
from app.services.rag.policy.session_tokens import sign_policy_session_id
from app.services.rag.policy.store import PolicyRagStore, shared_policy_store

EVAL_FIXTURE = Path(__file__).resolve().parent / "retrieval_dataset.json"
_SAMPLE_DIR_ENV = "POLICY_RAG_EVAL_SAMPLE_DIR"
_PHONE_RE = r"(?:\[\s*전화번호\s*\]|0\d{1,2}-?\d{3,4}-?\d{4}|1\d{3}-?\d{4})"


@dataclass(frozen=True)
class PolicyEvalCase:
    id: str
    query: str
    session_ids: tuple[str, ...]
    expected_session_id: str
    expected_term_groups: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class PolicyEvalCaseResult:
    case_id: str
    query: str
    passed: bool
    rank: int | None
    precision_at_k: float
    session_precision: float
    expected_session_id: str
    expected_term_groups: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class PolicyEvalReport:
    passed: int
    total: int
    reciprocal_rank_sum: float
    precision_at_k_sum: float
    session_precision_sum: float
    elapsed_seconds: float
    case_results: tuple[PolicyEvalCaseResult, ...]
    latency_seconds: tuple[float, ...]

    @property
    def recall(self) -> float:
        return self.passed / self.total if self.total else 0.0

    @property
    def mrr(self) -> float:
        return self.reciprocal_rank_sum / self.total if self.total else 0.0

    @property
    def precision_at_k(self) -> float:
        return self.precision_at_k_sum / self.total if self.total else 0.0

    @property
    def session_precision(self) -> float:
        return self.session_precision_sum / self.total if self.total else 0.0

    @property
    def average_latency_seconds(self) -> float:
        if not self.latency_seconds:
            return 0.0
        return sum(self.latency_seconds) / len(self.latency_seconds)


def evaluate_policy_retrieval(
    *,
    path: Path = EVAL_FIXTURE,
    sample_dir: Path | None = None,
    embedder: Embedder | None = None,
    top_k: int = 5,
    production: bool = False,
    store: PolicyRagStore | None = None,
    parse: Callable[[bytes], ParsedDocument] = parse_document,
) -> PolicyEvalReport:
    active_embedder = embedder or (
        openai_embedder_from_settings() if production else HashingEmbedder()
    )
    raw = json.loads(path.read_text(encoding="utf-8"))
    source_dir = _resolve_sample_dir(sample_dir, source=str(raw["source"]))
    cases = tuple(_case_from_json(item) for item in raw["cases"])
    if production:
        report = _evaluate_with_store(
            raw["documents"],
            cases,
            active_embedder,
            source_dir,
            top_k=top_k,
            store=store or shared_policy_store(),
            parse=parse,
        )
    else:
        created_at = datetime.now(UTC)
        records = _records_from_documents(
            raw["documents"],
            active_embedder,
            source_dir,
            parse=parse,
            created_at=created_at,
        )
        memory_store = _InMemoryPolicyStore(records)
        expires_at = created_at + timedelta(hours=1)
        report = _evaluate_cases(
            tuple(_case_with_session_tokens(case, expires_at=expires_at) for case in cases),
            top_k=top_k,
            retrieve=lambda case: retrieve_policy_context(
                list(case.session_ids),
                case.query,
                top_k=top_k,
                store=memory_store,
                embedder=active_embedder,
            ),
        )

    return PolicyEvalReport(
        passed=report.passed,
        total=report.total,
        reciprocal_rank_sum=report.reciprocal_rank_sum,
        precision_at_k_sum=report.precision_at_k_sum,
        session_precision_sum=report.session_precision_sum,
        elapsed_seconds=report.elapsed_seconds,
        case_results=report.case_results,
        latency_seconds=report.latency_seconds,
    )


def _evaluate_cases(
    cases: tuple[PolicyEvalCase, ...],
    *,
    top_k: int,
    retrieve: Callable[[PolicyEvalCase], list[PolicyRetrievalHit]],
) -> PolicyEvalReport:
    reciprocal_rank_sum = 0.0
    precision_at_k_sum = 0.0
    session_precision_sum = 0.0
    passed = 0
    case_results: list[PolicyEvalCaseResult] = []
    latencies: list[float] = []
    for case in cases:
        started = time.perf_counter()
        ranked = retrieve(case)[:top_k]
        latencies.append(time.perf_counter() - started)
        rank = _expected_rank(case, ranked)
        precision_at_k = _precision_at_k(case, ranked)
        session_precision = _session_precision(case, ranked)
        if rank is not None:
            passed += 1
            reciprocal_rank_sum += 1 / rank
        precision_at_k_sum += precision_at_k
        session_precision_sum += session_precision
        case_results.append(
            PolicyEvalCaseResult(
                case_id=case.id,
                query=case.query,
                passed=rank is not None,
                rank=rank,
                precision_at_k=precision_at_k,
                session_precision=session_precision,
                expected_session_id=case.expected_session_id,
                expected_term_groups=case.expected_term_groups,
            )
        )

    return PolicyEvalReport(
        passed=passed,
        total=len(cases),
        reciprocal_rank_sum=reciprocal_rank_sum,
        precision_at_k_sum=precision_at_k_sum,
        session_precision_sum=session_precision_sum,
        elapsed_seconds=sum(latencies),
        case_results=tuple(case_results),
        latency_seconds=tuple(latencies),
    )


def _evaluate_with_store(
    documents: list[dict[str, object]],
    cases: tuple[PolicyEvalCase, ...],
    embedder: Embedder,
    sample_dir: Path,
    *,
    top_k: int,
    store: PolicyRagStore,
    parse: Callable[[bytes], ParsedDocument],
) -> PolicyEvalReport:
    session_map = _eval_session_map(documents)
    created_at = datetime.now(UTC)
    records = _records_from_documents(
        documents,
        embedder,
        sample_dir,
        parse=parse,
        created_at=created_at,
        session_map=session_map,
    )
    eval_session_ids = tuple(session_map.values())
    expires_at = created_at + timedelta(hours=1)

    try:
        store.add(records)
        return _evaluate_cases(
            tuple(
                _case_with_session_tokens(
                    _mapped_case(case, session_map),
                    expires_at=expires_at,
                )
                for case in cases
            ),
            top_k=top_k,
            retrieve=lambda case: retrieve_policy_context(
                list(case.session_ids),
                case.query,
                top_k=top_k,
                store=store,
                embedder=embedder,
            ),
        )
    finally:
        for session_id in eval_session_ids:
            store.delete(session_id)


def _records_from_documents(
    documents: list[dict[str, object]],
    embedder: Embedder,
    sample_dir: Path,
    *,
    parse: Callable[[bytes], ParsedDocument],
    created_at: datetime,
    session_map: dict[str, str] | None = None,
) -> tuple[PolicyVectorRecord, ...]:
    records: list[PolicyVectorRecord] = []
    for raw in documents:
        original_session_id = str(raw["session_id"])
        session_id = (
            session_map.get(original_session_id, original_session_id)
            if session_map
            else original_session_id
        )
        pdf_path = sample_dir / str(raw["filename"])
        doc = parse(pdf_path.read_bytes())
        records.extend(
            build_policy_vector_records(
                doc,
                session_id=session_id,
                created_at=created_at,
                expires_at=created_at + timedelta(hours=1),
                embedder=embedder,
            )
        )
    return tuple(records)


class _InMemoryPolicyStore:
    def __init__(self, records: tuple[PolicyVectorRecord, ...]) -> None:
        self._records = list(records)

    def add(self, records: Sequence[PolicyVectorRecord]) -> None:
        self._records.extend(records)

    def query(
        self,
        session_ids: Sequence[str],
        query_embedding: tuple[float, ...],
        *,
        top_k: int,
    ) -> list[PolicyRetrievalHit]:
        allowed = set(session_ids)
        ranked = sorted(
            (record for record in self._records if record.chunk.session_id in allowed),
            key=lambda record: (-_cosine(query_embedding, record.embedding), record.chunk.id),
        )
        return [
            PolicyRetrievalHit(
                chunk=record.chunk,
                score=_cosine(query_embedding, record.embedding),
            )
            for record in ranked[:top_k]
        ]

    def extend(self, session_id: str, expires_at: datetime) -> bool:
        updated = False
        records: list[PolicyVectorRecord] = []
        for record in self._records:
            if record.chunk.session_id != session_id:
                records.append(record)
                continue
            updated = True
            records.append(
                PolicyVectorRecord(
                    chunk=replace(record.chunk, expires_at=expires_at),
                    embedding=record.embedding,
                )
            )
        self._records = records
        return updated

    def delete(self, session_id: str) -> None:
        self._records = [
            record for record in self._records if record.chunk.session_id != session_id
        ]


def _case_from_json(raw: dict[str, object]) -> PolicyEvalCase:
    session_ids = cast(list[object], raw["session_ids"])
    expected_term_groups_raw = cast(list[object] | None, raw.get("expected_term_groups"))
    expected_terms_raw = cast(list[object] | None, raw.get("expected_terms"))
    if expected_term_groups_raw is not None:
        expected_term_groups = tuple(
            tuple(str(term) for term in cast(list[object], group))
            for group in expected_term_groups_raw
        )
    elif expected_terms_raw is not None:
        expected_term_groups = tuple((str(item),) for item in expected_terms_raw)
    else:
        expected_term_groups = ((str(raw["expected_term"]),),)
    return PolicyEvalCase(
        id=str(raw["id"]),
        query=str(raw["query"]),
        session_ids=tuple(str(item) for item in session_ids),
        expected_session_id=str(raw["expected_session_id"]),
        expected_term_groups=expected_term_groups,
    )


def _eval_session_map(documents: list[dict[str, object]]) -> dict[str, str]:
    run_id = uuid.uuid4().hex[:12]
    return {str(raw["session_id"]): f"eval-{run_id}-{raw['session_id']}" for raw in documents}


def _mapped_case(case: PolicyEvalCase, session_map: dict[str, str]) -> PolicyEvalCase:
    return PolicyEvalCase(
        id=case.id,
        query=case.query,
        session_ids=tuple(session_map[session_id] for session_id in case.session_ids),
        expected_session_id=session_map[case.expected_session_id],
        expected_term_groups=case.expected_term_groups,
    )


def _case_with_session_tokens(case: PolicyEvalCase, *, expires_at: datetime) -> PolicyEvalCase:
    return PolicyEvalCase(
        id=case.id,
        query=case.query,
        session_ids=tuple(
            sign_policy_session_id(
                session_id,
                expires_at,
                max_expires_at=expires_at,
            )
            for session_id in case.session_ids
        ),
        expected_session_id=case.expected_session_id,
        expected_term_groups=case.expected_term_groups,
    )


def _expected_rank(case: PolicyEvalCase, hits: list[PolicyRetrievalHit]) -> int | None:
    for rank, hit in enumerate(hits, start=1):
        chunk = hit.chunk
        if chunk.session_id == case.expected_session_id and _text_matches_expected_group(
            chunk.text, case.expected_term_groups
        ):
            return rank
    return None


def _precision_at_k(case: PolicyEvalCase, hits: list[PolicyRetrievalHit]) -> float:
    if not hits:
        return 0.0
    relevant = sum(
        1
        for hit in hits
        if hit.chunk.session_id == case.expected_session_id
        and _text_matches_expected_group(hit.chunk.text, case.expected_term_groups)
    )
    return relevant / len(hits)


def _session_precision(case: PolicyEvalCase, hits: list[PolicyRetrievalHit]) -> float:
    if not hits:
        return 0.0
    return sum(1 for hit in hits if hit.chunk.session_id == case.expected_session_id) / len(hits)


def _text_matches_expected_group(
    text: str, expected_term_groups: tuple[tuple[str, ...], ...]
) -> bool:
    return any(
        all(_text_matches_expected(text, term) for term in group) for group in expected_term_groups
    )


def _text_matches_expected(text: str, expected_term: str) -> bool:
    if _normalize_match_text(expected_term) in _normalize_match_text(text):
        return True
    if expected_term == "[전화번호]":
        import re

        return re.search(_PHONE_RE, text) is not None
    return False


def _normalize_match_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return "".join(char for char in normalized if char.isalnum() or ("가" <= char <= "힣"))


def _resolve_sample_dir(sample_dir: Path | None, *, source: str) -> Path:
    if sample_dir is not None:
        return sample_dir

    env_value = os.getenv(_SAMPLE_DIR_ENV)
    if env_value:
        candidate = Path(env_value).expanduser().resolve()
        if candidate.is_dir():
            return candidate

    for root in _candidate_roots():
        candidate = root / source
        if candidate.is_dir():
            return candidate

    raise FileNotFoundError(
        f"could not find local sample directory '{source}'; set {_SAMPLE_DIR_ENV} to its path"
    )


def _candidate_roots() -> tuple[Path, ...]:
    repo_root = Path(__file__).resolve().parents[5]
    roots = [repo_root]

    try:
        output = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except Exception:
        output = ""

    for line in output.splitlines():
        if not line.startswith("worktree "):
            continue
        root = Path(line.removeprefix("worktree ").strip())
        if root not in roots:
            roots.append(root)
    return tuple(roots)


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


def _parse_args() -> tuple[bool, int]:
    parser = ArgumentParser(description="Evaluate uploaded-policy RAG retrieval.")
    parser.add_argument(
        "--production",
        action="store_true",
        help="Use the configured OpenAI embedding model instead of the local hashing embedder.",
    )
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    return bool(args.production), int(args.top_k)


if __name__ == "__main__":
    production, top_k = _parse_args()
    report = evaluate_policy_retrieval(production=production, top_k=top_k)
    print(
        f"passed={report.passed}/{report.total} "
        f"recall={report.recall:.3f} "
        f"precision@{top_k}={report.precision_at_k:.3f} "
        f"mrr={report.mrr:.3f} "
        f"session_precision={report.session_precision:.3f} "
        f"avg_s={report.average_latency_seconds:.2f}"
    )
    for result in report.case_results:
        status = "PASS" if result.passed else "FAIL"
        print(
            f"{status} {result.case_id} rank={result.rank} "
            f"precision={result.precision_at_k:.3f} "
            f"session_precision={result.session_precision:.3f}"
        )
