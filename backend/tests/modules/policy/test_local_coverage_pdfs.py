"""End-to-end coverage extraction against the repository's fictional sample policies.

Costs LLM calls, so it runs only when an OpenAI key is configured (same policy
as the other test_local_ files). This is the quality gate: every personal-
insurance sample policy must yield a non-empty coverage list. Core rows must
carry an amount and either policy wording or a generated explanation; name-only
rider/rate rows are tagged 부가 and intentionally keep amount/detail empty.

Every classified policy, including 자동차, runs through the same
coverage-extraction path. The auto sample is its own quality gate — see
test_local_auto_sample_extracts_detailed_coverages, which asserts verbatim
limits and descriptions on core coverages.
"""

import pytest

from app.core.config import get_settings
from app.modules.policy.coverage.service import STATUS_OK, extract_coverages
from app.modules.policy.parsing import parse_document
from tests.summary_helpers import SAMPLE_PDF_DIR

pytestmark = [
    pytest.mark.skipif(not SAMPLE_PDF_DIR.exists(), reason="local sample PDFs are not available"),
    pytest.mark.skipif(
        not get_settings().openai_api_key.get_secret_value(),
        reason="OPENAI_API_KEY is not configured",
    ),
]

SAMPLE_FILENAMES = [
    "01_건강보험_기본형.pdf",
    "02_건강보험_추가형.pdf",
    "03_자동차_운전자_복합보험.pdf",
    "04_여행_화재_복합보험.pdf",
]


@pytest.mark.parametrize("filename", SAMPLE_FILENAMES)
def test_local_samples_extract_nonempty_coverages(filename: str) -> None:
    doc = parse_document((SAMPLE_PDF_DIR / filename).read_bytes())
    coverages, status = extract_coverages(doc)

    assert status == STATUS_OK
    assert coverages, f"no coverages extracted from {filename}"
    for coverage in coverages:
        assert coverage["담보명"]
        if coverage.get("유형") == "부가":
            assert coverage["가입금액"] == ""
            assert coverage["보장내용"] is None
            assert coverage["해설"] is None
        else:
            assert coverage["가입금액"]
            assert coverage["보장내용"] or coverage["해설"], (
                f"{filename}::{coverage['담보명']} has neither policy wording nor explanation"
            )


def test_local_auto_sample_extracts_detailed_coverages() -> None:
    """자동차 policy: no golden 담보 list to assert against, so this checks the
    structural field-completeness policy instead — core coverages carry
    verbatim table limits and detail, and section headers aren't mistaken for
    rows.
    """
    doc = parse_document((SAMPLE_PDF_DIR / "03_자동차_운전자_복합보험.pdf").read_bytes())
    coverages, status = extract_coverages(doc)

    assert status == STATUS_OK
    core = [c for c in coverages if c.get("유형", "담보") == "담보"]
    assert core, "no core coverages extracted"
    # Core coverages' 가입금액 must carry the table's verbatim limit wording
    # (no longer demoted to 확인필요).
    demoted = [c["담보명"] for c in core if c["가입금액"] in {"", "확인필요"}]
    assert not demoted, f"core coverages missing verbatim limits: {demoted}"
    # Every coverage needs detail (either policy wording or a generated explanation).
    bare = [c["담보명"] for c in core if not (c["보장내용"] or c["해설"])]
    assert not bare, f"core coverages with no detail: {bare}"
    # Section headers must never surface as CORE coverages because they would
    # pollute totals and analysis.
    header_like_core = [c["담보명"] for c in core if "기타 특약" in c["담보명"]]
    assert not header_like_core, f"section headers extracted as core coverages: {header_like_core}"
