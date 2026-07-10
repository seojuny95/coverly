"""End-to-end coverage extraction against the real (gitignored) sample policies.

Costs LLM calls, so it runs only when an OpenAI key is configured (same policy
as the other test_local_ files). This is the quality gate: every sample policy
must yield a non-empty coverage list where each coverage has a name, an amount,
and either policy wording or a generated explanation.
"""

import pytest

from app.services.coverage.extraction import STATUS_OK, extract_coverages
from app.settings import get_settings
from tests.summary_helpers import SAMPLE_PDF_DIR

pytestmark = [
    pytest.mark.skipif(not SAMPLE_PDF_DIR.exists(), reason="local sample PDFs are not available"),
    pytest.mark.skipif(
        not get_settings().openai_api_key, reason="OPENAI_API_KEY is not configured"
    ),
]

# Personal-insurance policies only. Auto policies (자동차) are out of Phase 1
# scope — their document structure (riders/rates as coverages, standard-clause
# amounts) needs a dedicated path; the runtime returns an empty coverage list
# for them (see the auto-gate task).
SAMPLE_FILENAMES = [
    "DB운전자보험증권.pdf",
    "NH농협보험증권.pdf",
    "흥국보험증권.pdf",
]


@pytest.mark.parametrize("filename", SAMPLE_FILENAMES)
def test_local_samples_extract_nonempty_coverages(filename: str) -> None:
    coverages, status = extract_coverages((SAMPLE_PDF_DIR / filename).read_bytes())

    assert status == STATUS_OK
    assert coverages, f"no coverages extracted from {filename}"
    for coverage in coverages:
        assert coverage["담보명"]
        assert coverage["가입금액"]
        assert coverage["보장내용"] or coverage["해설"], (
            f"{filename}::{coverage['담보명']} has neither policy wording nor explanation"
        )
