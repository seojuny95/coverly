"""Coverage pipeline orchestrator: PDF bytes -> (보장목록, 분석상태).

Failure isolation lives here so the upload route stays thin: any error in
table detection or LLM normalization degrades to an empty list + 부분, and an
explanation failure keeps the extracted coverages (해설 stays None). This
function never raises.
"""

from collections.abc import Callable

from app.services.coverage.explain import explain_coverages
from app.services.coverage.normalize import normalize_coverages
from app.services.coverage.table import extract_coverage_source
from app.services.coverage.types import Coverage

STATUS_OK = "완료"
STATUS_PARTIAL = "부분"

Normalizer = Callable[[str], list[Coverage]]
Explainer = Callable[[list[str]], tuple[dict[str, str], bool]]


def extract_coverages(
    pdf_bytes: bytes,
    *,
    normalize: Normalizer = normalize_coverages,
    explain: Explainer = explain_coverages,
) -> tuple[list[Coverage], str]:
    """Extract the coverage list from a policy PDF, best-effort."""
    try:
        coverages = normalize(extract_coverage_source(pdf_bytes))
    except Exception:
        return [], STATUS_PARTIAL

    missing = [c["담보명"] for c in coverages if not c["보장내용"]]
    if not missing:
        return coverages, STATUS_OK

    explanations, ok = explain(missing)
    for coverage in coverages:
        if coverage["보장내용"] is None:
            coverage["해설"] = explanations.get(coverage["담보명"])
    return coverages, STATUS_OK if ok else STATUS_PARTIAL
