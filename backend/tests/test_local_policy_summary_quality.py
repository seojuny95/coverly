import json

import pytest

from app.services.pdf_text import extract_pdf_text
from app.services.summary import extract_policy_summary
from tests.summary_helpers import EXPECTED_PATH, SAMPLE_PDF_DIR, flatten_summary

pytestmark = pytest.mark.skipif(
    not SAMPLE_PDF_DIR.exists() or not EXPECTED_PATH.exists(),
    reason="local sample PDFs or expected summary manifest are not available",
)


def test_local_sample_policy_summary_field_accuracy() -> None:
    expected_payload = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))

    matched_fields = 0
    total_fields = 0
    mismatches: list[str] = []
    field_stats: dict[str, dict[str, int]] = {}

    for filename, expected_summary in expected_payload.items():
        pdf_path = SAMPLE_PDF_DIR / filename
        assert pdf_path.exists(), f"missing local sample PDF: {filename}"

        actual_summary = extract_policy_summary(extract_pdf_text(pdf_path.read_bytes()))
        flattened_expected = flatten_summary(expected_summary)
        flattened_actual = flatten_summary(actual_summary)

        for field_path, expected_value in flattened_expected.items():
            total_fields += 1
            stats = field_stats.setdefault(field_path, {"matched": 0, "total": 0})
            stats["total"] += 1

            actual_value = flattened_actual.get(field_path)
            if actual_value == expected_value:
                matched_fields += 1
                stats["matched"] += 1
                continue

            mismatches.append(
                f"{filename}::{field_path}: expected={expected_value!r}, actual={actual_value!r}"
            )

    accuracy = matched_fields / total_fields if total_fields else 1.0
    field_accuracy_lines = [
        f"{field_path}={stats['matched']}/{stats['total']}"
        for field_path, stats in sorted(field_stats.items())
    ]

    assert not mismatches, (
        "sample PDF summary mismatches detected\n"
        f"overall accuracy={matched_fields}/{total_fields} ({accuracy:.1%})\n"
        f"field accuracy: {', '.join(field_accuracy_lines)}\n" + "\n".join(mismatches)
    )
