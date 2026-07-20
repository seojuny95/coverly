"""Thin OpenAI boundary shared by LLM-backed services.

Isolates the network call behind the JsonCompleter type so services stay
testable — tests inject a plain function instead of hitting the API. Raises on
a missing key or API failure; callers isolate failures (the coverage pipeline
degrades to 확인필요/부분 instead of breaking the upload).
"""

import json
import os
from collections.abc import Callable
from functools import lru_cache
from typing import Any, cast

from openai import OpenAI
from pydantic import BaseModel

from app.core.config import get_settings

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
    """Publish the configured key so SDKs that read the environment can see it.

    pydantic-settings loads .env into Settings, not into os.environ, but the
    agents SDK builds its own OpenAI client from the environment. Without this
    the planner answers from .env while the agent fails at request time -- the
    app boots fine and only half of it works.

    A missing key is left absent rather than written as an empty string: the SDK
    would then fail as "invalid key" instead of "not configured". Nothing is
    raised here because every OpenAI call site already raises at use time.
    """

    api_key = get_settings().openai_api_key
    if api_key:
        os.environ["OPENAI_API_KEY"] = api_key
