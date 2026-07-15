"""Shared prompt-file loading helpers."""

from __future__ import annotations

from functools import cache
from pathlib import Path


@cache
def load_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()
