import pytest

from app.core.pii import (
    iter_resident_identifier_matches,
    mask_email_addresses,
    mask_phone_numbers,
    mask_resident_identifiers,
)


@pytest.mark.parametrize(
    "identifier",
    [
        "950524-1123456",
        "9505241123456",
        "950524 - 9******",
        "950524 4123456",
        "991332-9123456",
    ],
)
def test_masks_resident_identifier_shapes_without_validating_values(identifier: str) -> None:
    assert mask_resident_identifiers(identifier) == "[주민등록번호]"


def test_resident_identifier_matches_keep_source_order_and_groups() -> None:
    matches = list(iter_resident_identifier_matches("나 9505241123456 너 050524-4******"))

    assert [(match.group("birth"), match.group("code")) for match in matches] == [
        ("950524", "1"),
        ("050524", "4"),
    ]


@pytest.mark.parametrize(
    "phone",
    [
        "010-1234-5678",
        "010.1234.5678",
        "010 1234 5678",
        "0212345678",
        "02-123-4567",
        "1688-1234",
    ],
)
def test_masks_supported_phone_separators(phone: str) -> None:
    assert mask_phone_numbers(phone) == "[전화번호]"


def test_does_not_mask_large_amount_as_phone_number() -> None:
    assert mask_phone_numbers("가입금액 10000000원") == "가입금액 10000000원"


def test_masks_email_address() -> None:
    assert mask_email_addresses("연락처 a.person+tag@example.co.kr") == "연락처 [이메일]"
