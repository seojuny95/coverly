"""Load curated reference data from Postgres with bundled JSON fallback."""

import json
import logging
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

import psycopg

from app.settings import get_settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _database_reference_data() -> dict[str, object]:
    settings = get_settings()
    if not settings.reference_data_database_enabled or not settings.database_url:
        return {}

    try:
        with psycopg.connect(settings.database_url, connect_timeout=3) as connection:
            rows = connection.execute("SELECT key, payload FROM coverly.reference_data").fetchall()
    except (psycopg.Error, OSError, ValueError):
        logger.warning("Reference data database is unavailable; using bundled JSON")
        return {}

    return {str(key): payload for key, payload in rows}


def load_reference_data[T](
    key: str,
    fallback_path: Path,
    validate: Callable[[object], T],
) -> T:
    """Return validated database data, or the bundled fallback when unavailable."""

    database_payload = _database_reference_data().get(key)
    if database_payload is not None:
        try:
            return validate(database_payload)
        except (KeyError, TypeError, ValueError):
            logger.warning("Reference data '%s' is invalid; using bundled JSON", key)

    fallback_payload = json.loads(fallback_path.read_text(encoding="utf-8"))
    return validate(fallback_payload)
