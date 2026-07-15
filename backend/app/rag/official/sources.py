"""Official source registry for the official-source RAG corpus.

This file knows which official files exist, where they live, and whether their
local copies match the registry hash. It does not read document contents.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_ROOT = Path(__file__).resolve().parents[3] / "data"
REGISTRY_PATH = DATA_ROOT / "official-sources/source_registry.json"


@dataclass(frozen=True)
class OfficialSource:
    id: str
    title: str
    category: str
    publisher: str
    status: str
    rag_enabled: bool
    local_path: str | None = None
    source_url: str | None = None
    sha256: str | None = None
    effective_date: str | None = None
    published_date: str | None = None
    notes: str | None = None

    @property
    def absolute_path(self) -> Path | None:
        if not self.local_path:
            return None
        return DATA_ROOT / self.local_path

    @property
    def version_label(self) -> str:
        if self.effective_date:
            return f"시행일 {self.effective_date}"
        if self.published_date:
            return f"발행일 {self.published_date}"
        return "버전 미확인"


@lru_cache(maxsize=1)
def load_sources() -> tuple[OfficialSource, ...]:
    payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    return tuple(_parse_source(raw) for raw in payload.get("sources", []) if isinstance(raw, dict))


def rag_sources() -> tuple[OfficialSource, ...]:
    return tuple(source for source in load_sources() if source.rag_enabled)


def verify_downloaded_sources() -> list[str]:
    """Return validation errors for downloaded RAG sources."""
    errors: list[str] = []
    for source in rag_sources():
        if source.status != "downloaded":
            continue
        path = source.absolute_path
        if path is None or not path.exists():
            errors.append(f"{source.id}: local file is missing")
            continue
        if source.sha256:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != source.sha256:
                errors.append(f"{source.id}: sha256 mismatch")
    return errors


def _parse_source(raw: dict[str, Any]) -> OfficialSource:
    return OfficialSource(
        id=str(raw["id"]),
        title=str(raw["title"]),
        category=str(raw["category"]),
        publisher=str(raw["publisher"]),
        status=str(raw["status"]),
        rag_enabled=bool(raw.get("rag_enabled", False)),
        local_path=_optional_str(raw.get("local_path")),
        source_url=_optional_str(raw.get("source_url")),
        sha256=_optional_str(raw.get("sha256")),
        effective_date=_optional_str(raw.get("effective_date")),
        published_date=_optional_str(raw.get("published_date")),
        notes=_optional_str(raw.get("notes")),
    )


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
