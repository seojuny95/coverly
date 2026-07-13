"""Shared filesystem paths for service data files."""

from pathlib import Path

SERVICES_DIR = Path(__file__).resolve().parent
SERVICE_DATA_DIR = SERVICES_DIR / "data"
