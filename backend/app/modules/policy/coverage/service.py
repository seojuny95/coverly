"""Public orchestration service for policy coverage extraction."""

from collections.abc import Callable

from app.modules.policy.coverage import table_parsing
from app.modules.policy.coverage.explanation import explain_coverages_fast
from app.modules.policy.coverage.normalization import normalize_coverages as normalize_coverages
from app.modules.policy.models import Coverage, ParsedDocument

STATUS_OK = "완료"
STATUS_PARTIAL = "부분"

Normalizer = Callable[[str], list[Coverage]]
Explainer = Callable[[list[str]], tuple[dict[str, str], bool]]

# Keep this override on the public facade for callers that bound source size in tests.
_MAX_SOURCE_CHARS = table_parsing.DEFAULT_MAX_SOURCE_CHARS
normalize_table_coverages = table_parsing.normalize_table_coverages


def build_coverage_source(doc: ParsedDocument) -> str:
    """Build bounded coverage source text from a parsed policy document."""
    return table_parsing.build_coverage_source(doc, max_chars=_MAX_SOURCE_CHARS)


def _needs_explanation(coverage: Coverage) -> bool:
    """Return whether a substantive coverage lacks authoritative policy wording."""
    return not coverage["보장내용"] and coverage.get("유형", "담보") == "담보"


def extract_coverages(
    doc: ParsedDocument,
    *,
    normalize: Normalizer = normalize_coverages,
    explain: Explainer = explain_coverages_fast,
) -> tuple[list[Coverage], str]:
    """Extract and explain policy coverages without propagating stage failures."""
    try:
        source = build_coverage_source(doc)
        coverages = normalize(source)
    except Exception:
        return [], STATUS_PARTIAL

    if not coverages:
        status = STATUS_PARTIAL if source.strip() else STATUS_OK
        return [], status

    missing = [coverage["담보명"] for coverage in coverages if _needs_explanation(coverage)]
    if not missing:
        return coverages, STATUS_OK

    explanations, ok = explain(missing)
    for coverage in coverages:
        if _needs_explanation(coverage):
            coverage["해설"] = explanations.get(coverage["담보명"])
    return coverages, STATUS_OK if ok else STATUS_PARTIAL
