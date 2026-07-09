"""Coverage-table extraction against the real (gitignored) sample policies.

Detection is validated on real documents, not synthetic row lists — a
hand-crafted table that contains the exact header keywords would just mirror the
implementation. The behavior under test is: given a real policy PDF, produce a
markdown coverage-table source the LLM can map.
"""

import pytest

from app.services.coverage.table import extract_coverage_source
from tests.summary_helpers import SAMPLE_PDF_DIR

pytestmark = pytest.mark.skipif(
    not SAMPLE_PDF_DIR.exists(), reason="local sample PDFs are not available"
)

SAMPLE_FILENAMES = [
    "DB운전자보험증권.pdf",
    "NH농협보험증권.pdf",
    "현대해상자동차보험.pdf",
    "흥국보험증권.pdf",
]

_AMOUNT_HEADERS = ("가입금액", "보험가입금액", "보장금액", "보험금액", "한도")


@pytest.mark.parametrize("filename", SAMPLE_FILENAMES)
def test_extracts_markdown_coverage_source_from_real_policy(filename: str) -> None:
    source = extract_coverage_source((SAMPLE_PDF_DIR / filename).read_bytes())

    # A coverage table was detected and serialized as markdown (starts with a row),
    # and it carries an amount column — i.e. it is the coverage table, not prose.
    assert source.startswith("| "), f"{filename}: no markdown coverage table detected"
    assert any(header in source for header in _AMOUNT_HEADERS), (
        f"{filename}: detected table has no amount column"
    )
