from pathlib import Path

import pytest

from app.services.pdf_text import extract_pdf_text
from app.services.policy_document import classify_policy_document

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_PDF_DIR = REPO_ROOT / "sample-insurance-input"

pytestmark = pytest.mark.skipif(
    not SAMPLE_PDF_DIR.exists(),
    reason="local sample PDFs are not available",
)


def test_local_sample_policy_pdfs_are_detected_as_policies() -> None:
    pdf_paths = sorted(SAMPLE_PDF_DIR.glob("*.pdf"))
    assert pdf_paths, "expected at least one local sample PDF"

    for pdf_path in pdf_paths:
        text = extract_pdf_text(pdf_path.read_bytes())
        signal = classify_policy_document(text)

        assert signal.is_likely_policy is True, (
            f"{pdf_path.name}: expected policy detection, score={signal.score}, "
            f"matched_terms={signal.matched_terms}"
        )
        assert signal.score >= 7, (
            f"{pdf_path.name}: expected a meaningful policy score, got {signal.score}"
        )
