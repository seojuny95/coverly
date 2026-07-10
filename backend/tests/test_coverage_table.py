"""Coverage-table extraction against the real (gitignored) sample policies.

Detection is validated on real documents, not synthetic row lists — a
hand-crafted table that contains the exact header keywords would just mirror the
implementation. The behavior under test is: given a real policy PDF, produce a
markdown coverage-table source the LLM can map.
"""

import pytest

from app.services.coverage import table as table_module
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


def test_wrapped_cell_lines_rejoined_with_a_space_not_merged_or_slashed() -> None:
    # NH cells wrap across visual lines (e.g. "수술을\n받은 경우"). Rejoin with a
    # space so distinct words are not merged ("수술을받은"), and never with the old
    # " / " marker, which leaked into 보장내용 as a stray slash. Only "\n" is
    # rewritten, so a genuine "/" in the policy text is never touched.
    source = extract_coverage_source((SAMPLE_PDF_DIR / "NH농협보험증권.pdf").read_bytes())

    assert "수술을 받은" in source
    assert "수술을받은" not in source
    assert " / " not in source


def test_source_is_capped_to_the_max_length(monkeypatch: pytest.MonkeyPatch) -> None:
    # The tier-3 fallback can dump every page's layout text, so the source fed to
    # the LLM must be bounded — a large PDF must not blow up model input and cost.
    monkeypatch.setattr(table_module, "_MAX_SOURCE_CHARS", 50)

    source = extract_coverage_source((SAMPLE_PDF_DIR / "흥국보험증권.pdf").read_bytes())

    assert len(source) == 50
