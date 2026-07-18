"""Shared lexical helpers for RAG retrieval."""

from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣]+")


def tokenize(text: str) -> tuple[str, ...]:
    """Tokenize searchable text and add Korean character n-grams."""

    tokens = [token.casefold() for token in _TOKEN_RE.findall(text) if token.strip()]
    for token in tuple(tokens):
        if any("가" <= char <= "힣" for char in token):
            tokens.extend(character_ngrams(token))
    return tuple(dict.fromkeys(tokens))


def character_ngrams(text: str) -> tuple[str, ...]:
    """Return 2-to-4 character slices for lexical matching."""

    if len(text) < 2:
        return ()
    ngrams: list[str] = []
    for size in (2, 3, 4):
        if len(text) < size:
            continue
        ngrams.extend(text[index : index + size] for index in range(len(text) - size + 1))
    return tuple(ngrams)
