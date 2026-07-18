import pytest

from app.modules.portfolio.amounts import parse_amount
from app.modules.portfolio.schemas import CoverageInput


@pytest.mark.parametrize(
    ("display_amount", "expected"),
    [
        ("1,000 원", 1_000),
        ("2천원", 2_000),
        ("1.5만원", 15_000),
        ("3백만원", 3_000_000),
        ("2천만원", 20_000_000),
        ("1.25억원", 125_000_000),
    ],
)
def test_parse_amount_supports_all_units_and_decimal_values(
    display_amount: str,
    expected: int,
) -> None:
    coverage = CoverageInput(담보명="테스트 담보", 가입금액=display_amount)

    assert parse_amount(coverage) == expected


def test_parse_amount_prefers_confirmed_numeric_amount() -> None:
    coverage = CoverageInput(
        담보명="테스트 담보",
        가입금액="해석할 수 없는 값",
        가입금액숫자=12_345,
    )

    assert parse_amount(coverage) == 12_345


@pytest.mark.parametrize(
    "display_amount",
    [
        "",
        "가입금액 참조",
        "만원",
        "1.2.3만원",
        "1.2345천원",
        "-1만원",
    ],
)
def test_parse_amount_rejects_unknown_or_non_integer_values(display_amount: str) -> None:
    coverage = CoverageInput(담보명="테스트 담보", 가입금액=display_amount)

    assert parse_amount(coverage) is None
