from app.modules.coverage import taxonomy as coverage_taxonomy
from app.modules.coverage.purpose import coverage_purpose
from app.modules.evidence.catalog import is_safe_confirmed_fact

_CATEGORIES = (
    coverage_taxonomy.CANCER,
    coverage_taxonomy.CEREBRO,
    coverage_taxonomy.HEART,
    coverage_taxonomy.INJURY_DISABILITY,
    coverage_taxonomy.DISEASE_DISABILITY,
    coverage_taxonomy.HOSPITAL,
    coverage_taxonomy.SURGERY,
    coverage_taxonomy.DEATH,
    coverage_taxonomy.INDEMNITY,
    coverage_taxonomy.CARE,
)


def test_every_life_stage_category_has_a_purpose() -> None:
    for category in _CATEGORIES:
        assert coverage_purpose(category) is not None


def test_purposes_pass_the_grounding_filter() -> None:
    for category in _CATEGORIES:
        purpose = coverage_purpose(category)
        assert purpose is not None
        assert is_safe_confirmed_fact(purpose)


def test_unknown_category_returns_none() -> None:
    assert coverage_purpose("존재하지 않는 분류") is None
