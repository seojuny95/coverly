"""Import bundled reference data into the Coverly private Postgres schema."""

import json
from pathlib import Path

import psycopg

from app.settings import get_settings

BACKEND_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BACKEND_DIR / "app" / "services" / "data"
DATASETS = {
    "claim_channels": DATA_DIR / "claim_channels.json",
    "classification_rules": DATA_DIR / "classification_rules.json",
    "coverage_matching_rules": DATA_DIR / "coverage_matching_rules.json",
    "disclosure_links": DATA_DIR / "disclosure_links.json",
    "insurer_catalog": DATA_DIR / "insurer_catalog.json",
}


def main() -> None:
    database_url = get_settings().database_url
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")

    rows: list[tuple[str, object, str]] = []
    for key, path in DATASETS.items():
        payload: object = json.loads(path.read_text(encoding="utf-8"))
        source = str(path.relative_to(BACKEND_DIR.parent))
        rows.append((key, payload, source))

    values = [
        (key, json.dumps(payload, ensure_ascii=False), source) for key, payload, source in rows
    ]
    with (
        psycopg.connect(database_url) as connection,
        connection.cursor() as cursor,
    ):
        cursor.executemany(
            """
            INSERT INTO coverly.reference_data (key, payload, source)
            VALUES (%s, %s::jsonb, %s)
            ON CONFLICT (key) DO UPDATE
            SET payload = EXCLUDED.payload,
                source = EXCLUDED.source
            """,
            values,
        )

    print(f"Synced {len(rows)} reference data sets")


if __name__ == "__main__":
    main()
