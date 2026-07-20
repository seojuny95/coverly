import os

import pytest

from app.core.config import Settings
from app.integrations.openai import client


def _settings(monkeypatch: pytest.MonkeyPatch, key: str) -> None:
    monkeypatch.setattr(client, "get_settings", lambda: Settings(openai_api_key=key))


def test_agent_sdk_reads_the_key_from_settings_not_the_ambient_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # pydantic-settings loads .env into Settings, never into os.environ, but the
    # agents SDK builds its own client from the environment. Without this wiring
    # the planner works from .env while the agent fails at request time.
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    _settings(monkeypatch, "test-key")

    client.configure_agent_sdk_credentials()

    assert os.environ.get("OPENAI_API_KEY") == "test-key"


def test_missing_key_does_not_clobber_an_already_exported_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "exported-key")
    _settings(monkeypatch, "")

    client.configure_agent_sdk_credentials()

    assert os.environ.get("OPENAI_API_KEY") == "exported-key"
