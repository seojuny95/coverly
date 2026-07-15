import json

from app.modules.reference_data import reference_data_path
from scripts.seed_reference_data import BACKEND_DIR, DATASETS, load_seed_rows


def test_seed_rows_use_current_bundled_reference_data() -> None:
    assert reference_data_path("claim_channels.json") == DATASETS["claim_channels"]
    assert reference_data_path("disclosure_links.json") == DATASETS["disclosure_links"]

    rows = {key: (json.loads(payload), source) for key, payload, source in load_seed_rows()}

    assert set(rows) == set(DATASETS)
    for key, path in DATASETS.items():
        payload, source = rows[key]
        assert payload
        assert source == str(path.relative_to(BACKEND_DIR.parent))
