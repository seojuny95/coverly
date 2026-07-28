"""Live Agent+RAG integration evaluation.

The suite runs the real ``POST /qa/stream`` route and real Agent tool loop.
Only the portfolio session and RAG stores are replaced with fixed evaluation
fixtures. ``production`` mode uses temporary Policy pgvector rows and the
configured Official pgvector index.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from app.core.config import get_settings
from app.modules.portfolio.schemas import PolicyInput
from evals.qa.reporting import collect_reports, print_report, result_payload
from evals.qa.runner import (
    Recorder,
    TurnResult,
    build_client,
    run_case,
)
from evals.qa_rag.dataset import QaRagDataset, case_payload, load_qa_rag_dataset
from evals.qa_rag.providers import rag_provider_context
from evals.rag.execution import RetrievalMode

_HERE = Path(__file__).parent
_BACKEND_ROOT = _HERE.parent.parent
_REPO_ROOT = _BACKEND_ROOT.parent
_DATASET_PATH = _HERE / "dataset.json"
_OFFICIAL_SOURCE_ROOT = _BACKEND_ROOT / "data" / "official-sources"
_FINGERPRINT_ROOTS = (
    _BACKEND_ROOT / "app",
    _BACKEND_ROOT / "evals" / "qa",
    _BACKEND_ROOT / "evals" / "qa_rag",
)
_FINGERPRINT_FILES = (
    _BACKEND_ROOT / "app" / "core" / "config.py",
    _BACKEND_ROOT / "app" / "rag" / "embeddings.py",
    _BACKEND_ROOT / "app" / "rag" / "lexical.py",
    _BACKEND_ROOT / "app" / "rag" / "scoring.py",
    _BACKEND_ROOT / "app" / "rag" / "text.py",
    _BACKEND_ROOT / "app" / "integrations" / "openai" / "client.py",
    _BACKEND_ROOT / "app" / "integrations" / "postgres" / "official_rag_store.py",
    _BACKEND_ROOT / "app" / "integrations" / "postgres" / "policy_rag_store.py",
    _BACKEND_ROOT / "evals" / "rag" / "execution.py",
    _BACKEND_ROOT / "evals" / "rag" / "policy" / "retrieval.py",
)


def _load_fixture_policies(relative_path: str) -> tuple[PolicyInput, ...]:
    raw = json.loads((_BACKEND_ROOT / relative_path).read_text(encoding="utf-8"))
    return tuple(PolicyInput.model_validate(item) for item in raw)


def _evaluation_fingerprint(dataset: QaRagDataset) -> str:
    paths = _evaluation_fingerprint_paths(dataset)
    digest = hashlib.sha256()
    for path in paths:
        digest.update(str(path.relative_to(_REPO_ROOT)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def _evaluation_fingerprint_paths(dataset: QaRagDataset) -> tuple[Path, ...]:
    paths = {
        _DATASET_PATH,
        _BACKEND_ROOT / dataset.fixture,
        _BACKEND_ROOT / dataset.policy_retrieval_dataset,
        *_FINGERPRINT_FILES,
        *sorted(path for path in _OFFICIAL_SOURCE_ROOT.rglob("*") if path.is_file()),
        *_policy_source_paths(dataset),
    }
    for root in _FINGERPRINT_ROOTS:
        suffixes = {".py", ".json"}
        if root.is_relative_to(_BACKEND_ROOT / "app"):
            suffixes.add(".md")
        paths.update(path for path in root.rglob("*") if path.is_file() and path.suffix in suffixes)
    return tuple(sorted(paths, key=lambda path: str(path.relative_to(_REPO_ROOT))))


def _policy_source_paths(dataset: QaRagDataset) -> tuple[Path, ...]:
    retrieval_dataset_path = _BACKEND_ROOT / dataset.policy_retrieval_dataset
    raw = json.loads(retrieval_dataset_path.read_text(encoding="utf-8"))
    source_root = _REPO_ROOT / str(raw["source"])
    return tuple(source_root / str(document["filename"]) for document in raw["documents"])


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, math.ceil(len(ordered) * 0.95))
    return ordered[rank - 1]


def _agent_usage(results: list[TurnResult]) -> dict[str, int]:
    return {
        "requests": sum(result.agent_usage.requests for result in results),
        "input_tokens": sum(result.agent_usage.input_tokens for result in results),
        "output_tokens": sum(result.agent_usage.output_tokens for result in results),
        "total_tokens": sum(result.agent_usage.total_tokens for result in results),
    }


def _summary(
    results: list[TurnResult],
    *,
    runs: int,
    retrieval_mode: RetrievalMode,
    selected_set: str,
    judge_enabled: bool,
    expected_total: int,
    dataset: QaRagDataset,
    rag_stats: dict[str, int | float | str],
) -> dict[str, object]:
    latencies = [result.elapsed_seconds for result in results]
    passed = sum(result.passed for result in results)
    execution_failures = sum(result.execution_error is not None for result in results)
    return {
        "dataset_version": dataset.version,
        "evaluation_fingerprint": _evaluation_fingerprint(dataset),
        "generated_at": datetime.now(UTC).isoformat(),
        "model": get_settings().openai_model,
        "retrieval_mode": retrieval_mode,
        "set": selected_set,
        "judge_enabled": judge_enabled,
        "runs": runs,
        "passed": passed,
        "total": len(results),
        "expected_total": expected_total,
        "execution_failures": execution_failures,
        "pass_rate": passed / len(results) if results else 0.0,
        "average_latency_seconds": (
            round(sum(latencies) / len(latencies), 3) if latencies else 0.0
        ),
        "p95_latency_seconds": round(_p95(latencies), 3),
        "agent_model_usage": _agent_usage(results),
        "rag": rag_stats,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run live Agent+RAG evaluation")
    parser.add_argument("--case", action="append", help="case id (repeatable)")
    parser.add_argument("--runs", type=int, default=1, help="repeat every case N times")
    parser.add_argument("--judge", action="store_true", help="also run the LLM judge rubrics")
    parser.add_argument(
        "--set",
        choices=("all", "practice", "test"),
        default="all",
        help="dataset split to run",
    )
    parser.add_argument(
        "--retrieval-mode",
        choices=("offline", "production"),
        default="offline",
    )
    parser.add_argument("--json", dest="json_path", help="write the report as JSON")
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be at least 1")
    return args


def main() -> None:
    args = _parse_args()
    retrieval_mode = cast(RetrievalMode, args.retrieval_mode)
    dataset = load_qa_rag_dataset(_DATASET_PATH)
    cases = dataset.cases
    if args.set != "all":
        cases = [case for case in cases if case.set == args.set]
    if args.case:
        wanted = set(args.case)
        unknown = wanted - {case.id for case in dataset.cases}
        if unknown:
            raise SystemExit(f"unknown case ids: {sorted(unknown)}")
        cases = [case for case in cases if case.id in wanted]

    policies = _load_fixture_policies(dataset.fixture)
    policy_dataset_path = _BACKEND_ROOT / dataset.policy_retrieval_dataset
    policy_session_ids = tuple(dataset.policy_session_ids)
    rubric_descriptions = dataset.judge_rubrics
    results: list[TurnResult] = []

    with rag_provider_context(
        mode=retrieval_mode,
        policy_dataset_path=policy_dataset_path,
    ) as providers:
        recorder = Recorder(providers.configure_context)
        with build_client(
            recorder,
            policies,
            rag_session_ids=policy_session_ids,
        ) as client:
            for run_index in range(1, args.runs + 1):
                for case in cases:
                    suffix = f" ({run_index}/{args.runs})" if args.runs > 1 else ""
                    print(f"▶ {case.id}{suffix}", flush=True)
                    results.extend(
                        run_case(
                            client,
                            recorder,
                            case_payload(case),
                            policies=policies,
                            rubric_descriptions=rubric_descriptions,
                            run_judge=args.judge,
                        )
                    )

        rag_stats = providers.stats.as_dict(retrieval_mode=retrieval_mode)

    expected_total = sum(len(case.turns) for case in cases) * args.runs
    if len(results) != expected_total:
        raise RuntimeError(
            f"evaluation result count mismatch: expected={expected_total}, actual={len(results)}"
        )

    print_report(collect_reports(results), args.runs)
    summary = _summary(
        results,
        runs=args.runs,
        retrieval_mode=retrieval_mode,
        selected_set=args.set,
        judge_enabled=args.judge,
        expected_total=expected_total,
        dataset=dataset,
        rag_stats=rag_stats,
    )
    print(
        " ".join(
            [
                f"passed={summary['passed']}/{summary['total']}",
                f"pass_rate={summary['pass_rate']:.3f}",
                f"avg={summary['average_latency_seconds']:.3f}s",
                f"p95={summary['p95_latency_seconds']:.3f}s",
            ]
        )
    )

    if args.json_path:
        payload = {
            "summary": summary,
            "results": [result_payload(result) for result in results],
        }
        Path(args.json_path).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"JSON: {args.json_path}")


if __name__ == "__main__":
    main()
