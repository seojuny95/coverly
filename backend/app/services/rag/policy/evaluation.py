"""Offline retrieval evaluation for uploaded-policy RAG."""

from __future__ import annotations

import json
import os
import subprocess
from argparse import ArgumentParser
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

from app.services.parsing import parse_document
from app.services.rag.embeddings import Embedder, HashingEmbedder, openai_embedder_from_settings
from app.services.rag.policy.indexing import build_policy_vector_records
from app.services.rag.policy.models import PolicyVectorRecord
from app.services.types import ParsedDocument

EVAL_FIXTURE = Path(__file__).resolve().parent / "evaluation_dataset.json"
_SAMPLE_DIR_ENV = "POLICY_RAG_EVAL_SAMPLE_DIR"


@dataclass(frozen=True)
class PolicyEvalCase:
    id: str
    query: str
    session_ids: tuple[str, ...]
    expected_session_id: str
    expected_term: str


@dataclass(frozen=True)
class PolicyEvalCaseResult:
    case_id: str
    query: str
    passed: bool
    rank: int | None
    expected_session_id: str
    expected_term: str


@dataclass(frozen=True)
class PolicyEvalReport:
    passed: int
    total: int
    reciprocal_rank_sum: float
    case_results: tuple[PolicyEvalCaseResult, ...]

    @property
    def recall(self) -> float:
        return self.passed / self.total if self.total else 0.0

    @property
    def mrr(self) -> float:
        return self.reciprocal_rank_sum / self.total if self.total else 0.0


def evaluate_policy_retrieval(
    *,
    path: Path = EVAL_FIXTURE,
    sample_dir: Path | None = None,
    embedder: Embedder | None = None,
    top_k: int = 5,
    production: bool = False,
    parse: Callable[[bytes], ParsedDocument] = parse_document,
) -> PolicyEvalReport:
    active_embedder = embedder or (
        openai_embedder_from_settings() if production else HashingEmbedder()
    )
    raw = json.loads(path.read_text(encoding="utf-8"))
    source_dir = _resolve_sample_dir(sample_dir, source=str(raw["source"]))
    records = _records_from_documents(raw["documents"], active_embedder, source_dir, parse=parse)
    cases = tuple(_case_from_json(item) for item in raw["cases"])

    reciprocal_rank_sum = 0.0
    passed = 0
    case_results: list[PolicyEvalCaseResult] = []
    for case in cases:
        ranked = _rank(case.query, case.session_ids, records, active_embedder)[:top_k]
        rank = _expected_rank(case, ranked)
        if rank is not None:
            passed += 1
            reciprocal_rank_sum += 1 / rank
        case_results.append(
            PolicyEvalCaseResult(
                case_id=case.id,
                query=case.query,
                passed=rank is not None,
                rank=rank,
                expected_session_id=case.expected_session_id,
                expected_term=case.expected_term,
            )
        )

    return PolicyEvalReport(
        passed=passed,
        total=len(cases),
        reciprocal_rank_sum=reciprocal_rank_sum,
        case_results=tuple(case_results),
    )


def _records_from_documents(
    documents: list[dict[str, object]],
    embedder: Embedder,
    sample_dir: Path,
    *,
    parse: Callable[[bytes], ParsedDocument],
) -> tuple[PolicyVectorRecord, ...]:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    records: list[PolicyVectorRecord] = []
    for raw in documents:
        pdf_path = sample_dir / str(raw["filename"])
        doc = parse(pdf_path.read_bytes())
        records.extend(
            build_policy_vector_records(
                doc,
                session_id=str(raw["session_id"]),
                created_at=now,
                expires_at=now + timedelta(hours=1),
                embedder=embedder,
            )
        )
    return tuple(records)


def _case_from_json(raw: dict[str, object]) -> PolicyEvalCase:
    session_ids = cast(list[object], raw["session_ids"])
    return PolicyEvalCase(
        id=str(raw["id"]),
        query=str(raw["query"]),
        session_ids=tuple(str(item) for item in session_ids),
        expected_session_id=str(raw["expected_session_id"]),
        expected_term=str(raw["expected_term"]),
    )


def _rank(
    query: str,
    session_ids: tuple[str, ...],
    records: tuple[PolicyVectorRecord, ...],
    embedder: Embedder,
) -> list[PolicyVectorRecord]:
    query_embedding = embedder.embed_texts([query])[0]
    allowed = set(session_ids)
    candidates = [record for record in records if record.chunk.session_id in allowed]
    return sorted(
        candidates,
        key=lambda record: (-_cosine(query_embedding, record.embedding), record.chunk.id),
    )


def _expected_rank(case: PolicyEvalCase, records: list[PolicyVectorRecord]) -> int | None:
    for rank, record in enumerate(records, start=1):
        chunk = record.chunk
        if chunk.session_id == case.expected_session_id and case.expected_term in chunk.text:
            return rank
    return None


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
    print(f"passed={report.passed}/{report.total} recall={report.recall:.3f} mrr={report.mrr:.3f}")
    for result in report.case_results:
        status = "PASS" if result.passed else "FAIL"
        print(f"{status} {result.case_id} rank={result.rank}")
