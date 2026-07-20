import pytest

from app.core.config import Settings
from app.integrations.openai import client


def _settings(monkeypatch: pytest.MonkeyPatch, key: str) -> None:
    monkeypatch.setattr(client, "get_settings", lambda: Settings(openai_api_key=key))


def test_agent_sdk_gets_the_key_without_touching_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # pydantic-settings loads .env into Settings, not into os.environ, so the SDK
    # would otherwise build its client without a key. Hand it over through the
    # SDK's own entry point rather than exporting a secret process-wide.
    recorded: dict[str, object] = {}
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        client,
        "set_default_openai_key",
        lambda key, use_for_tracing: recorded.update(key=key, use_for_tracing=use_for_tracing),
    )
    monkeypatch.setattr(
        client, "set_tracing_disabled", lambda disabled: recorded.update(tracing_disabled=disabled)
    )
    _settings(monkeypatch, "test-key")

    client.configure_agent_sdk_credentials()

    assert recorded["key"] == "test-key"
    assert recorded["use_for_tracing"] is False
    assert "OPENAI_API_KEY" not in __import__("os").environ


def test_tracing_is_disabled_so_conversations_are_not_exported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: dict[str, object] = {}
    monkeypatch.setattr(client, "set_default_openai_key", lambda key, use_for_tracing: None)
    monkeypatch.setattr(
        client, "set_tracing_disabled", lambda disabled: recorded.update(disabled=disabled)
    )
    _settings(monkeypatch, "test-key")

    client.configure_agent_sdk_credentials()

    assert recorded["disabled"] is True


def test_a_missing_key_still_disables_tracing(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: dict[str, object] = {}
    monkeypatch.setattr(
        client, "set_default_openai_key", lambda key, use_for_tracing: recorded.update(called=True)
    )
    monkeypatch.setattr(
        client, "set_tracing_disabled", lambda disabled: recorded.update(disabled=disabled)
    )
    _settings(monkeypatch, "")

    client.configure_agent_sdk_credentials()

    assert recorded.get("called") is None
    assert recorded["disabled"] is True
