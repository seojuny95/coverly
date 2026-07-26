"""Validate the local sample reference-data seed against runtime contracts."""

import json
import re
from pathlib import Path

from app.modules.coverage.disclosure_links import _validate_directory as validate_disclosures
from app.modules.portfolio.death_benefit_guides import _validate_payload as validate_death_guides
from app.modules.portfolio.essential_guides import (
    _validate_essential_coverage_guides as validate_essential_guides,
)
from app.modules.reference_data.claim_channels import _validate_directory as validate_claims
from app.modules.reference_data.insurers import (
    _validate_contact_data,
    _validate_insurer_candidates,
)

_SEED_PATH = Path(__file__).parents[4] / "supabase" / "seed.sql"
_PAYLOAD_PATTERN = re.compile(
    r"'(?P<key>"
    r"claim_channels|death_benefit_guides|disclosure_links|"
    r"essential_coverage_guides|insurer_catalog"
    r")',\s*"
    r"\$json\$(?P<payload>.*?)\$json\$::jsonb",
    re.DOTALL,
)


def _seed_payloads() -> dict[str, object]:
    sql = _SEED_PATH.read_text(encoding="utf-8")
    return {
        match.group("key"): json.loads(match.group("payload"))
        for match in _PAYLOAD_PATTERN.finditer(sql)
    }


def test_local_seed_contains_valid_required_payloads() -> None:
    payloads = _seed_payloads()

    claims = validate_claims(payloads["claim_channels"])
    _validate_contact_data(payloads["claim_channels"])
    validate_disclosures(payloads["disclosure_links"])
    validate_death_guides(payloads["death_benefit_guides"])
    validate_essential_guides(payloads["essential_coverage_guides"])
    insurer_catalog = _validate_insurer_candidates(payloads["insurer_catalog"])

    insurers = {
        entry["보험사"]
        for entry in claims["보험사"]
        if isinstance(entry, dict) and isinstance(entry.get("보험사"), str)
    }
    assert insurers == {
        "DB손해보험",
        "NH농협손해보험",
        "삼성화재",
        "한화손해보험",
        "현대해상",
        "흥국화재",
    }
    assert {"커버리샘플생명", "커버리샘플손해보험"} <= set(insurer_catalog)
