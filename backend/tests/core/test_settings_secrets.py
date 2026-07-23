import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings
from app.core.limits import MAX_PORTFOLIO_DOCUMENTS

_OPENAI_API_KEY = "sk-test-should-never-be-printed"
_DATABASE_URL = "postgresql://user:hunter2@example/test"
_SESSION_SECRET = "test-policy-rag-session-secret-32"


def _settings() -> Settings:
    return Settings(
        openai_api_key=SecretStr(_OPENAI_API_KEY),
        database_url=SecretStr(_DATABASE_URL),
        policy_rag_session_secret=SecretStr(_SESSION_SECRET),
    )


def test_settings_repr_hides_secret_values() -> None:
    """A failing assertion that embeds Settings must not dump live credentials
    into pytest output, and from there into CI logs."""
    settings = _settings()

    rendered = f"{settings!r} {settings}"

    for secret in (_OPENAI_API_KEY, _DATABASE_URL, _SESSION_SECRET):
        assert secret not in rendered


def test_secret_values_stay_readable() -> None:
    settings = _settings()

    assert settings.openai_api_key.get_secret_value() == _OPENAI_API_KEY
    assert settings.database_url.get_secret_value() == _DATABASE_URL
    assert settings.policy_rag_session_secret.get_secret_value() == _SESSION_SECRET


def test_portfolio_document_limit_is_a_fixed_product_contract() -> None:
    assert _settings().portfolio_session_max_documents == MAX_PORTFOLIO_DOCUMENTS

    with pytest.raises(ValidationError):
        Settings(portfolio_session_max_documents=MAX_PORTFOLIO_DOCUMENTS + 1)


def test_pdf_parser_capacity_is_independent_from_the_product_document_limit() -> None:
    settings = Settings(pdf_parsing_max_concurrency=3)

    assert settings.portfolio_session_max_documents == MAX_PORTFOLIO_DOCUMENTS
    assert settings.pdf_parsing_max_concurrency == 3
