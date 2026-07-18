"""Backward-compatible import path for official-source PDF chunking."""

from __future__ import annotations

from app.rag.official.chunkers import build_chunks
from app.rag.official.sources import OfficialSource

__all__ = ["OfficialSource", "build_chunks"]
