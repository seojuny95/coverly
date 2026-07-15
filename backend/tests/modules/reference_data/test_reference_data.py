import json
from pathlib import Path

import pytest

from app.modules.reference_data import loader as reference_data


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
    monkeypatch.setattr(reference_data, "_database_enabled", lambda: True)

    result = reference_data.load_reference_data(
        "example", fallback, _require_mapping, owner="database"
    )

    assert result == {"source": "database"}


def test_invalid_database_reference_data_does_not_use_bundled_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fallback = tmp_path / "fallback.json"
    fallback.write_text(json.dumps({"source": "file"}), encoding="utf-8")
    monkeypatch.setattr(
        reference_data,
        "_database_reference_data",
        lambda: {"example": ["invalid"]},
    )
    monkeypatch.setattr(reference_data, "_database_enabled", lambda: True)

    with pytest.raises(reference_data.ReferenceDataUnavailableError):
        reference_data.load_reference_data("example", fallback, _require_mapping, owner="database")


def test_code_owned_reference_data_ignores_database_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundled = tmp_path / "bundled.json"
    bundled.write_text(json.dumps({"source": "code"}), encoding="utf-8")
    monkeypatch.setattr(
        reference_data,
        "_database_reference_data",
        lambda: {"example": {"source": "database"}},
    )

    result = reference_data.load_reference_data("example", bundled, _require_mapping)

    assert result == {"source": "code"}
