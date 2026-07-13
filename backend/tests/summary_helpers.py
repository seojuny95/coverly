import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_PDF_DIR = REPO_ROOT / "sample-insurance-input"
EXPECTED_PATH = SAMPLE_PDF_DIR / "expected-policy-summary.local.json"


def _load_required_display_values() -> dict[str, dict[str, Any]]:
    if not EXPECTED_PATH.exists():
        return {}

    with EXPECTED_PATH.open(encoding="utf-8") as file:
        loaded = json.load(file)

    if not isinstance(loaded, dict):
        raise TypeError("local expected policy summary fixture must be an object")

    return loaded


REQUIRED_DISPLAY_VALUES = _load_required_display_values()


def flatten_summary(summary: Mapping[str, object], prefix: str = "") -> dict[str, object]:
    flattened: dict[str, object] = {}
    for key, value in summary.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            flattened.update(flatten_summary(value, path))
            continue
        flattened[path] = value

    return flattened
