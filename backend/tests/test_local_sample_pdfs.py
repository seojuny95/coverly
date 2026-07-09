import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.summary_helpers import REQUIRED_DISPLAY_VALUES, SAMPLE_PDF_DIR, flatten_summary

pytestmark = pytest.mark.skipif(
    not SAMPLE_PDF_DIR.exists(),
    reason="local sample PDFs are not available",
)


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

    assert not missing_or_wrong_fields, (
        "parse response is missing required display fields\n" + "\n".join(missing_or_wrong_fields)
    )
