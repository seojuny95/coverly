"""OpenAI completion boundary used by application modules."""

from app.integrations.openai.client import (
    JsonCompleter,
    compact_prompt_text,
    configure_agent_sdk_credentials,
    dump_prompt_json,
    embed_texts,
    structured_completer,
)

__all__ = [
    "JsonCompleter",
    "compact_prompt_text",
    "configure_agent_sdk_credentials",
    "dump_prompt_json",
    "embed_texts",
    "structured_completer",
]
