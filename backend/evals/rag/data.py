"""Shared input coercion helpers for RAG evaluation fixtures."""

from __future__ import annotations

from typing import cast


def string_tuple(value: object) -> tuple[str, ...]:
    """Coerce a JSON array to an immutable tuple of strings."""

    return tuple(str(item) for item in cast(list[object], value))


def string_groups(value: object) -> tuple[tuple[str, ...], ...]:
    """Coerce nested JSON arrays to immutable string groups."""

    return tuple(string_tuple(group) for group in cast(list[object], value))
