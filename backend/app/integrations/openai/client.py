"""Thin OpenAI boundary shared by LLM-backed services.

Isolates the network call behind the JsonCompleter type so services stay
testable — tests inject a plain function instead of hitting the API. Raises on
a missing key or API failure; callers isolate failures (the coverage pipeline
degrades to 확인필요/부분 instead of breaking the upload).
"""

import json
from collections.abc import Callable
from functools import lru_cache
from typing import Any, cast

from agents import set_default_openai_key, set_tracing_disabled
from openai import OpenAI
from openai.types.responses import EasyInputMessageParam
from pydantic import BaseModel

from app.core.config import get_settings

ConversationMessage = EasyInputMessageParam
"""One message in a conversation sent to a model.

Re-exported so feature modules can build model input without importing the
vendor package directly, which the architecture tests forbid.
"""

JsonCompleter = Callable[[str, str], dict[str, object]]

_TIMEOUT_S = 30.0
_MAX_RETRIES = 2


@lru_cache
def _get_client(api_key: str) -> OpenAI:
    return OpenAI(api_key=api_key, timeout=_TIMEOUT_S, max_retries=_MAX_RETRIES)


def structured_completer(
    schema: type[BaseModel],
    *,
    model: str | None = None,
) -> JsonCompleter:
    """Build a completer that constrains the model's output to `schema`."""

    def complete(system: str, user: str) -> dict[str, object]:
        settings = get_settings()
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")

        response = _get_client(settings.openai_api_key).responses.parse(
            model=model or settings.openai_model,
            input=cast(
                Any,
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            ),
            text_format=schema,
            temperature=0,
        )

        parsed = response.output_parsed
        return parsed.model_dump(mode="json") if parsed else {}

    return complete


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed texts through the configured OpenAI embedding model."""
    if not texts:
        return []

    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    response = _get_client(settings.openai_api_key).embeddings.create(
        model=settings.openai_embedding_model,
        input=texts,
        dimensions=settings.openai_embedding_dimensions,
    )

    return [list(item.embedding) for item in response.data]


def compact_prompt_text(text: str, max_chars: int) -> str:
    """Normalize excerpt whitespace and cap prompt context with an ellipsis."""

    compact = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 1].rstrip() + "…"


def dump_prompt_json(payload: object) -> str:
    """Serialize prompt payloads consistently across LLM call sites."""

    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_agent_sdk_credentials() -> None:
    """Hand the configured key to the agents SDK and switch its tracing off.

    pydantic-settings loads .env into Settings, not into os.environ, so the SDK
    would otherwise build its client without a key. Passing it through the SDK's
    own entry point avoids exporting a secret process-wide, where child
    processes and environment dumps would pick it up.

    Tracing is disabled because it ships the conversation -- the user's question
    and the policy facts the tools returned -- to OpenAI's trace store. That is
    an export of personal data the product never asked for, and it is on by
    default in this SDK.
    """

    set_tracing_disabled(True)

    api_key = get_settings().openai_api_key
    if api_key:
        set_default_openai_key(api_key, use_for_tracing=False)
