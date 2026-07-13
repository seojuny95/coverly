"""Shared text normalization and splitting helpers for RAG pipelines."""

from __future__ import annotations

import re

_WHITESPACE_RE = re.compile(r"[ \t]+")
_MAX_PAGE_CHUNK_CHARS = 1400


def normalize_text(text: str) -> str:
    lines = [_WHITESPACE_RE.sub(" ", line).strip() for line in text.splitlines()]
    kept: list[str] = []
    for line in lines:
        if line:
            kept.append(line)
        elif kept and kept[-1] != "":
            kept.append("")
    return "\n".join(kept).strip()


def split_within_char_limit(text: str) -> list[str]:
    if len(text) <= _MAX_PAGE_CHUNK_CHARS:
        return [text]
    units = [unit.strip() for unit in text.split("\n\n") if unit.strip()]
    return _pack_units(units) or [text[:_MAX_PAGE_CHUNK_CHARS]]


def _pack_units(units: list[str]) -> list[str]:
    """Greedily pack units under the size cap, splitting oversized units first."""
    blocks: list[str] = []
    current = ""
    for unit in units:
        for piece in _fit_unit(unit):
            candidate = f"{current}\n{piece}" if current else piece
            if current and len(candidate) > _MAX_PAGE_CHUNK_CHARS:
                blocks.append(current)
                current = piece
                continue
            current = candidate
    if current:
        blocks.append(current)
    return blocks


def _fit_unit(unit: str) -> list[str]:
    """Split one over-cap unit by line, then hard-slice as a last resort."""
    if len(unit) <= _MAX_PAGE_CHUNK_CHARS:
        return [unit]

    lines = [line.strip() for line in unit.split("\n") if line.strip()]
    if len(lines) > 1:
        return _pack_units(lines)

    return [
        unit[start : start + _MAX_PAGE_CHUNK_CHARS]
        for start in range(0, len(unit), _MAX_PAGE_CHUNK_CHARS)
    ]
