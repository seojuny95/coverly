from pathlib import Path

import pytest

from app.services.parsing import parse_document
from app.services.summary import extract_policy_summary

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_PDF_DIR = REPO_ROOT / "sample-insurance-input"

pytestmark = pytest.mark.skipif(
    not SAMPLE_PDF_DIR.exists(),
    reason="local sample PDFs are not available",
)


def test_local_sample_policy_pdfs_match_expected_contract_terms() -> None:
    expectations = {
        "DB운전자보험증권.pdf": {
            "납입기간": "20년납",
            "만기일": "2044-07-26",
        },
        "NH농협보험증권.pdf": {
            "납입기간": "20년납",
            "만기일": "2095-04-29",
        },
        "흥국보험증권.pdf": {
            "납입기간": "20년납",
            "만기일": "2095-05-06",
        },
    }

    for filename, expected in expectations.items():
        pdf_path = SAMPLE_PDF_DIR / filename
        assert pdf_path.exists(), f"missing local sample PDF: {filename}"

        text = parse_document(pdf_path.read_bytes()).text
        summary = extract_policy_summary(text)

        assert summary.get("납입기간") == expected["납입기간"], filename
        assert summary.get("만기일") == expected["만기일"], filename
