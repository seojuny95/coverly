import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_PDF_DIR = REPO_ROOT / "sample-insurance-input"
EXPECTED_PATH = SAMPLE_PDF_DIR / "expected-policy-summary.local.json"

pytestmark = pytest.mark.skipif(
    not SAMPLE_PDF_DIR.exists() or not EXPECTED_PATH.exists(),
    reason="local sample PDFs or expected summary manifest are not available",
)


def test_local_sample_pdfs_match_expected_summary() -> None:
    client = TestClient(app)
    expected_payload = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))

    for filename, expected_summary in expected_payload.items():
        pdf_path = SAMPLE_PDF_DIR / filename
        assert pdf_path.exists(), f"missing local sample PDF: {filename}"

        response = client.post(
            "/policies/parse",
            files={"file": (pdf_path.name, pdf_path.read_bytes(), "application/pdf")},
        )

        assert response.status_code == 200, f"{filename}: expected upload acceptance"

        payload = response.json()
        assert payload["status"] == "accepted", f"{filename}: expected accepted status"
        assert payload["문서판정"]["보험증권추정"] is True, f"{filename}: expected policy detection"
        assert payload["기본정보"] == expected_summary, (
            f"{filename}: extracted summary does not match local expected values"
        )
