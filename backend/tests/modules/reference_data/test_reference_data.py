import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from app.modules.reference_data import loader as reference_data


def _require_mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("mapping required")
    return value


def test_database_reference_data_returns_database_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        reference_data,
        "_database_reference_data",
        lambda: {"example": {"source": "database"}},
    )

    result = reference_data.load_database_reference_data("example", _require_mapping)

    assert result == {"source": "database"}


def test_missing_database_reference_data_fails_without_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(reference_data, "_database_reference_data", lambda: {})

    with pytest.raises(reference_data.ReferenceDataUnavailableError):
        reference_data.load_database_reference_data("example", _require_mapping)


def test_invalid_database_reference_data_fails_without_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        reference_data,
        "_database_reference_data",
        lambda: {"example": ["invalid"]},
    )

    with pytest.raises(reference_data.ReferenceDataUnavailableError):
        reference_data.load_database_reference_data("example", _require_mapping)


def test_database_reference_data_requires_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        reference_data,
        "get_settings",
        lambda: SimpleNamespace(reference_data_database_enabled=True, database_url=SecretStr("")),
    )

    with pytest.raises(reference_data.ReferenceDataUnavailableError):
        reference_data._database_url()


def test_database_reference_data_requires_enabled_database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        reference_data,
        "get_settings",
        lambda: SimpleNamespace(
            reference_data_database_enabled=False,
            database_url=SecretStr("postgresql://example"),
        ),
    )

    with pytest.raises(reference_data.ReferenceDataUnavailableError):
        reference_data._database_url()


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
