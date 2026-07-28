"""Live 상담 Agent evaluation against fixed portfolio facts.

Runs every case through the real ``POST /qa/stream`` route. The portfolio
session store is the only runtime dependency replaced by a fixture.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, cast

from app.modules.portfolio.schemas import PolicyInput
from evals.qa.reporting import collect_reports, print_report, result_payload
from evals.qa.runner import (
    Recorder,
    build_client,
    run_case,
)

_HERE = Path(__file__).parent
_BACKEND_ROOT = _HERE.parent.parent
_DATASET_PATH = _HERE / "dataset.json"


def _load_dataset() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(_DATASET_PATH.read_text(encoding="utf-8")))


def _load_fixture_policies(relative_path: str) -> tuple[PolicyInput, ...]:
    raw = json.loads((_BACKEND_ROOT / relative_path).read_text(encoding="utf-8"))
    return tuple(PolicyInput.model_validate(item) for item in raw)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run live qa eval cases")
    parser.add_argument("--case", action="append", help="case id (repeatable)")
    parser.add_argument("--runs", type=int, default=1, help="repeat every case N times")
    parser.add_argument("--judge", action="store_true", help="also run the LLM judge rubrics")
    parser.add_argument("--json", dest="json_path", help="write full results as JSON")
    args = parser.parse_args()

    dataset = _load_dataset()
    cases = dataset["cases"]
    if args.case:
        wanted = set(args.case)
        cases = [case for case in cases if case["id"] in wanted]

    policies = _load_fixture_policies(str(dataset["fixture"]))
    rubric_descriptions = dataset.get("judge_rubrics", {})
    recorder = Recorder()
    results = []

    # Entering TestClient runs the lifespan that configures Agents SDK credentials.
    with build_client(recorder, policies) as client:
        for run_index in range(1, args.runs + 1):
            for case in cases:
                suffix = f" ({run_index}/{args.runs})" if args.runs > 1 else ""
                print(f"▶ {case['id']}{suffix}", flush=True)
                try:
                    results.extend(
                        run_case(
                            client,
                            recorder,
                            case,
                            policies=policies,
                            rubric_descriptions=rubric_descriptions,
                            run_judge=args.judge,
                        )
                    )
                except Exception as error:  # noqa: BLE001 - report, don't abort the suite
                    print(f"  ! 실행 실패: {error}", flush=True)

    print_report(collect_reports(results), args.runs)

    if args.json_path:
        payload = [result_payload(result) for result in results]
        Path(args.json_path).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"JSON: {args.json_path}")


if __name__ == "__main__":
    main()
