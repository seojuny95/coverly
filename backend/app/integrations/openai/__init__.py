"""OpenAI completion boundary used by application modules."""

from app.integrations.openai.client import (
    Embedder,
    JsonCompleter,
    TextStreamer,
    compact_prompt_text,
    dump_prompt_json,
    embed_texts,
    search_official_web,
    stream_completion,
    structured_completer,
)

__all__ = [
    "Embedder",
    "JsonCompleter",
    "TextStreamer",
    "compact_prompt_text",
    "dump_prompt_json",
    "embed_texts",
    "search_official_web",
    "stream_completion",
    "structured_completer",
]
