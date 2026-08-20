from pydantic import SecretStr

from app.core.config import Settings


def test_langsmith_values_are_hidden_from_settings_repr() -> None:
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        langsmith_api_key=SecretStr("private-key"),
        langsmith_endpoint="https://private.example.com",
        langsmith_project="private-project",
        langsmith_environment="private-environment",
        langsmith_release="private-release",
    )

    rendered = repr(settings)

    assert "private-key" not in rendered
    assert "private.example.com" not in rendered
    assert "private-project" not in rendered
    assert "private-environment" not in rendered
    assert "private-release" not in rendered
