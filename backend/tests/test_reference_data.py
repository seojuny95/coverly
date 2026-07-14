import json
from pathlib import Path

import pytest

from app.services import reference_data


def _require_mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("mapping required")
    return value


def test_database_reference_data_wins_over_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fallback = tmp_path / "fallback.json"
    fallback.write_text(json.dumps({"source": "file"}), encoding="utf-8")
    monkeypatch.setattr(
        reference_data,
        "_database_reference_data",
        lambda: {"example": {"source": "database"}},
    )

    result = reference_data.load_reference_data("example", fallback, _require_mapping)

    assert result == {"source": "database"}


def test_invalid_database_reference_data_uses_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fallback = tmp_path / "fallback.json"
    fallback.write_text(json.dumps({"source": "file"}), encoding="utf-8")
    monkeypatch.setattr(
        reference_data,
        "_database_reference_data",
        lambda: {"example": ["invalid"]},
    )

    result = reference_data.load_reference_data("example", fallback, _require_mapping)

    assert result == {"source": "file"}
