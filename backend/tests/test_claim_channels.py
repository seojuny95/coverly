"""Deterministic claim-channel directory lookup (curated data, not RAG)."""

from app.services.claim_channels import channels_for


def test_channels_for_matches_insurer_by_containment() -> None:
    result = channels_for(["삼성화재해상보험"], has_indemnity=False)

    assert result.insurers
    assert result.insurers[0].name == "삼성화재"
    assert result.insurers[0].customer_center
    assert result.indemnity is None


def test_channels_for_prepends_indemnity_service_when_holding_indemnity() -> None:
    result = channels_for(["삼성화재"], has_indemnity=True)

    assert result.indemnity is not None
    assert result.indemnity.name == "실손24"


def test_channels_for_dedupes_and_skips_unknown_insurers() -> None:
    result = channels_for(["삼성화재", "삼성화재", "존재하지않는보험"], has_indemnity=False)

    assert len(result.insurers) == 1
    assert result.insurers[0].name == "삼성화재"
