"""Load curated reference data from its declared source of truth."""

import json
import logging
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

import psycopg

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class ReferenceDataUnavailableError(RuntimeError):
    """Raised when database-owned reference data cannot be loaded safely."""


def _database_url() -> str:
    settings = get_settings()
    if not settings.reference_data_database_enabled:
        raise ReferenceDataUnavailableError("Database reference data is disabled")
    if not settings.database_url:
        raise ReferenceDataUnavailableError("DATABASE_URL is required for database reference data")
    return settings.database_url


@lru_cache(maxsize=1)
def _database_reference_data() -> dict[str, object]:
    with psycopg.connect(_database_url(), connect_timeout=3) as connection:
        rows = connection.execute("SELECT key, payload FROM reference.reference_data").fetchall()

    return {str(key): payload for key, payload in rows}


def load_reference_data[T](
    key: str,
    bundled_path: Path,
    validate: Callable[[object], T],
) -> T:
    """Return validated code-owned reference data."""

    bundled_payload = json.loads(bundled_path.read_text(encoding="utf-8"))
    return validate(bundled_payload)


def load_database_reference_data[T](
    key: str,
    validate: Callable[[object], T],
) -> T:
    """Return validated Supabase-owned reference data without a bundled fallback."""

    try:
        database_payload = _database_reference_data().get(key)
    except ReferenceDataUnavailableError:
        raise
    except (psycopg.Error, OSError, ValueError) as exc:
        logger.exception("database_reference_data_unavailable", extra={"reference_key": key})
        raise ReferenceDataUnavailableError(
            f"Database reference data '{key}' is unavailable"
        ) from exc
    if database_payload is None:
        raise ReferenceDataUnavailableError(f"Database reference data '{key}' is missing")
    try:
        return validate(database_payload)
    except (KeyError, TypeError, ValueError) as exc:
        raise ReferenceDataUnavailableError(f"Database reference data '{key}' is invalid") from exc
