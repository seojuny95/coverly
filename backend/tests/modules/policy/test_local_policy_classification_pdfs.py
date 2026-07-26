import pytest

from app.modules.policy.classification import classify_policy
from app.modules.policy.parsing import parse_document
from app.modules.policy.summary.service import extract_policy_summary
from tests.summary_helpers import SAMPLE_PDF_DIR

pytestmark = pytest.mark.skipif(
    not SAMPLE_PDF_DIR.exists(),
    reason="local sample PDFs are not available",
)


def test_local_sample_policy_pdfs_match_expected_classification() -> None:
    expectations = {
        "01_건강보험_기본형.pdf": {
            "보험분류": "제3보험",
            "상품태그포함": {"질병보험"},
            "상품태그제외": {"운전자보험", "실손의료보험"},
        },
        "02_건강보험_추가형.pdf": {
            "보험분류": "제3보험",
            "상품태그포함": {"질병보험"},
            "상품태그제외": {"운전자보험", "실손의료보험"},
        },
        "03_자동차_운전자_복합보험.pdf": {
            "보험분류": "손해보험",
            "상품태그포함": {"자동차보험", "운전자보험"},
            "상품태그제외": {"실손의료보험", "종신보험"},
        },
        "04_여행_화재_복합보험.pdf": {
            "보험분류": "손해보험",
            "상품태그포함": {"여행자보험", "화재보험"},
            "상품태그제외": {"운전자보험", "실손의료보험", "종신보험"},
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
