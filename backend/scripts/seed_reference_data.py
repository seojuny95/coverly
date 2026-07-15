"""Seed missing operational reference data into the private Postgres schema."""

import json
from pathlib import Path

import psycopg

from app.core.config import get_settings
from app.modules.reference_data import reference_data_path

BACKEND_DIR = Path(__file__).resolve().parents[1]
DATASETS = {
    "claim_channels": reference_data_path("claim_channels.json"),
    "disclosure_links": reference_data_path("disclosure_links.json"),
}


def load_seed_rows() -> list[tuple[str, str, str]]:
    """Load bundled seed payloads with repository-relative source paths."""
    rows: list[tuple[str, str, str]] = []
    for key, path in DATASETS.items():
        payload: object = json.loads(path.read_text(encoding="utf-8"))
        source = str(path.relative_to(BACKEND_DIR.parent))
        serialized_payload = json.dumps(payload, ensure_ascii=False)
        rows.append((key, serialized_payload, source))
    return rows


def main() -> None:
    database_url = get_settings().database_url
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")

    rows = load_seed_rows()
    with (
        psycopg.connect(database_url) as connection,
        connection.cursor() as cursor,
    ):
        cursor.executemany(
            """
            INSERT INTO coverly.reference_data (key, payload, source)
            VALUES (%s, %s::jsonb, %s)
            ON CONFLICT (key) DO NOTHING
            """,
            rows,
        )

    print(f"Reference data seed completed for {len(rows)} data sets")


if __name__ == "__main__":
    main()
