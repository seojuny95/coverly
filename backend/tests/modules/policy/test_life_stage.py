import pytest

from app.modules.policy.life_stage import life_stage_for_age


@pytest.mark.parametrize(
    ("age", "expected"),
    [
        (0, "어린이"),
        (18, "어린이"),
        (19, "성인"),
        (64, "성인"),
        (65, "시니어"),
        (120, "시니어"),
    ],
)
def test_life_stage_boundaries(age: int, expected: str) -> None:
    assert life_stage_for_age(age) == expected
