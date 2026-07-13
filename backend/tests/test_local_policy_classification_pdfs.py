from pathlib import Path

import pytest

from app.services.policy.classification import classify_policy
from app.services.policy.parsing import parse_document
from app.services.policy.summary.service import extract_policy_summary

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_PDF_DIR = REPO_ROOT / "sample-insurance-input"

pytestmark = pytest.mark.skipif(
    not SAMPLE_PDF_DIR.exists(),
    reason="local sample PDFs are not available",
)


def test_local_sample_policy_pdfs_match_expected_classification() -> None:
    expectations = {
        "DB운전자보험증권.pdf": {
            "보험분류": "배상·화재·기타",
            "상품태그포함": {"운전자"},
            "상품태그제외": {"실손", "종신"},
        },
        "NH농협보험증권.pdf": {
            "보험분류": "상해·질병·실손",
            "상품태그포함": {"상해", "어린이"},
            "상품태그제외": {"운전자", "실손"},
        },
        "현대해상자동차보험.pdf": {
            "보험분류": "자동차",
            "상품태그포함": {"자동차"},
            "상품태그제외": {"운전자", "실손", "종신"},
        },
        "흥국보험증권.pdf": {
            "보험분류": "상해·질병·실손",
            "상품태그포함": {"상해", "질병", "어린이"},
            "상품태그제외": {"운전자", "실손"},
        },
    }

    for filename, expected in expectations.items():
        pdf_path = SAMPLE_PDF_DIR / filename
        assert pdf_path.exists(), f"missing local sample PDF: {filename}"

        text = parse_document(pdf_path.read_bytes()).text
        summary = extract_policy_summary(text)
        result = classify_policy(
            text=text,
            product_name=summary.get("상품명"),
        )

        assert result["보험분류"] == expected["보험분류"], filename
        assert set(result["상품태그"]).issuperset(expected["상품태그포함"]), filename
        assert set(result["상품태그"]).isdisjoint(expected["상품태그제외"]), filename
