"""Thin OpenAI boundary shared by coverage services.

Isolates the network call behind the JsonCompleter type so services stay
testable — tests inject a plain function instead of hitting the API. Raises on
a missing key or API failure; callers isolate failures (the coverage pipeline
degrades to 확인필요/부분 instead of breaking the upload).
"""

from collections.abc import Callable
from functools import lru_cache
from typing import Any, cast

from openai import OpenAI
from pydantic import BaseModel

from app.settings import get_settings

JsonCompleter = Callable[[str, str], dict[str, object]]

_TIMEOUT_S = 30.0
_MAX_RETRIES = 2


@lru_cache
def _get_client(api_key: str) -> OpenAI:
    return OpenAI(api_key=api_key, timeout=_TIMEOUT_S, max_retries=_MAX_RETRIES)


def structured_completer(schema: type[BaseModel]) -> JsonCompleter:
    """Build a completer that constrains the model's output to `schema`."""

    def complete(system: str, user: str) -> dict[str, object]:
        settings = get_settings()
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        response = _get_client(settings.openai_api_key).responses.parse(
            model=settings.openai_model,
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
