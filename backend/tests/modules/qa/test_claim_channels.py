"""Deterministic claim-channel directory lookup (curated data, not RAG)."""

from app.modules.qa.claim_channels import channels_for


def test_channels_for_matches_canonical_catalog_name_to_directory_name() -> None:
    result = channels_for(["현대해상화재보험"], include_medical_indemnity_service=False)

    assert result.insurers
    assert result.insurers[0].name == "현대해상"
    assert result.insurers[0].customer_center
    assert result.medical_indemnity is None


def test_channels_for_adds_service_when_requested() -> None:
    result = channels_for(["삼성화재"], include_medical_indemnity_service=True)

    assert result.medical_indemnity is not None
    assert result.medical_indemnity.name == "실손24"


def test_channels_for_dedupes_and_skips_unknown_insurers() -> None:
    result = channels_for(
        ["삼성화재", "삼성화재", "존재하지않는보험"],
        include_medical_indemnity_service=False,
    )

    assert len(result.insurers) == 1
    assert result.insurers[0].name == "삼성화재"


def test_channels_for_does_not_guess_unknown_partial_insurer_name() -> None:
    result = channels_for(["삼성화재해상보험"], include_medical_indemnity_service=False)

    assert result.insurers == ()
