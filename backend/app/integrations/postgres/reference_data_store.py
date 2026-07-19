"""Postgres reads for operational reference-data payloads."""

import psycopg


class ReferenceDataStoreError(RuntimeError):
    """The operational reference-data table could not be read."""


def load_reference_payloads(database_url: str) -> dict[str, object]:
    try:
        with psycopg.connect(database_url, connect_timeout=3) as connection:
            rows = connection.execute(
                "SELECT key, payload FROM reference.reference_data"
            ).fetchall()
    except (psycopg.Error, OSError) as exc:
        raise ReferenceDataStoreError("Operational reference data is unavailable") from exc
    return {str(key): payload for key, payload in rows}
