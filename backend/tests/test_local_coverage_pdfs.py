"""End-to-end coverage extraction against the real (gitignored) sample policies.

Costs LLM calls, so it runs only when an OpenAI key is configured (same policy
as the other test_local_ files). This is the quality gate: every personal-
insurance sample policy must yield a non-empty coverage list where each
coverage has a name, an amount, and either policy wording or a generated
explanation.

The auto-policy skip has been removed: every classified policy, including
자동차, now runs through the same coverage-extraction path. Auto policies
(riders/rates laid out as coverages, standard-clause amounts) are new
territory for this path, so the auto sample is checked separately against
looser invariants (no crash, valid status, schema-valid rows) rather than the
non-empty quality gate — see test_local_auto_sample_coverage_extraction_is_well_formed.
"""

import pytest

from app.services.coverage import STATUS_OK, STATUS_PARTIAL, extract_coverages
from app.services.parsing import parse_document
from app.settings import get_settings
from tests.summary_helpers import SAMPLE_PDF_DIR

pytestmark = [
    pytest.mark.skipif(not SAMPLE_PDF_DIR.exists(), reason="local sample PDFs are not available"),
    pytest.mark.skipif(
        not get_settings().openai_api_key, reason="OPENAI_API_KEY is not configured"
    ),
]

SAMPLE_FILENAMES = [
    "DB운전자보험증권.pdf",
    "NH농협보험증권.pdf",
    "흥국보험증권.pdf",
]


@pytest.mark.parametrize("filename", SAMPLE_FILENAMES)
def test_local_samples_extract_nonempty_coverages(filename: str) -> None:
    doc = parse_document((SAMPLE_PDF_DIR / filename).read_bytes())
    coverages, status = extract_coverages(doc)

    assert status == STATUS_OK
    assert coverages, f"no coverages extracted from {filename}"
    for coverage in coverages:
        assert coverage["담보명"]
        assert coverage["가입금액"]
        assert coverage["보장내용"] or coverage["해설"], (
            f"{filename}::{coverage['담보명']} has neither policy wording nor explanation"
        )


def test_local_auto_sample_coverage_extraction_is_well_formed() -> None:
    """자동차 policy: no golden 담보 rows to assert against, so this checks
    invariants only. An empty coverage list + 부분 (degrade) is acceptable;
    a non-empty, schema-valid list is a bonus, not a requirement.
    """
    doc = parse_document((SAMPLE_PDF_DIR / "현대해상자동차보험.pdf").read_bytes())
    coverages, status = extract_coverages(doc)

    assert status in {STATUS_OK, STATUS_PARTIAL}
    for coverage in coverages:
        assert coverage["담보명"]
        assert coverage["가입금액"]
