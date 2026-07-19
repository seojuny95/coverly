"""Load curated reference data from its declared source of truth."""

import json
import logging
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings
from app.integrations.postgres.reference_data_store import (
    ReferenceDataStoreError,
    load_reference_payloads,
)

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
    return load_reference_payloads(_database_url())


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
    except (ReferenceDataStoreError, ValueError) as exc:
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
