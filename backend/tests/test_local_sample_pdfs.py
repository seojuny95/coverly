import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.summary_helpers import REQUIRED_DISPLAY_VALUES, SAMPLE_PDF_DIR, flatten_summary

pytestmark = pytest.mark.skipif(
    not SAMPLE_PDF_DIR.exists(),
    reason="local sample PDFs are not available",
)

_STATUS_VALUES = {"완료", "부분"}


def test_local_sample_parse_response_includes_required_display_values() -> None:
    client = TestClient(app)
    missing_or_wrong_fields: list[str] = []

    for filename, required_values in REQUIRED_DISPLAY_VALUES.items():
        pdf_path = SAMPLE_PDF_DIR / filename
        assert pdf_path.exists(), f"missing local sample PDF: {filename}"

        response = client.post(
            "/policies/parse",
            files={"file": (pdf_path.name, pdf_path.read_bytes(), "application/pdf")},
        )

        assert response.status_code == 200, f"{filename}: expected upload acceptance"

        payload = response.json()
        flattened_summary = flatten_summary(payload["기본정보"])

        for field_path, expected_value in required_values.items():
            actual_value = flattened_summary.get(field_path)
            if actual_value == expected_value:
                continue

            missing_or_wrong_fields.append(
                f"{filename}::{field_path}: expected={expected_value!r}, actual={actual_value!r}"
            )

        assert payload["분석상태"] in _STATUS_VALUES, f"{filename}: unexpected 분석상태"
        assert payload["보장목록"], f"{filename}: expected non-empty coverage list"
        for coverage in payload["보장목록"]:
            assert coverage["담보명"], f"{filename}: coverage row missing 담보명"
            # 부가 rows (auto policy riders) are name-only by design — an empty
            # 가입금액 is their expected shape and no 해설 is generated. Every
            # 담보 row needs an amount plus policy wording or 해설.
            if coverage.get("유형", "담보") == "담보":
                assert coverage["가입금액"], f"{filename}: coverage row missing 가입금액"
                assert coverage["보장내용"] or coverage["해설"], (
                    f"{filename}::{coverage['담보명']} has neither policy wording nor explanation"
                )

    assert not missing_or_wrong_fields, (
        "parse response is missing required display fields\n" + "\n".join(missing_or_wrong_fields)
    )
