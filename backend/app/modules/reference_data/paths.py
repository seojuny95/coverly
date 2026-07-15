"""Filesystem paths for bundled reference data."""

from pathlib import Path

REFERENCE_DATA_DIR = Path(__file__).resolve().parent / "data"


def reference_data_path(filename: str) -> Path:
    """Return the path to a bundled reference data file."""

    return REFERENCE_DATA_DIR / filename
