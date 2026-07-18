from app.modules.qa.pii import mask_qa_pii


def test_qa_pii_uses_shared_phone_and_identifier_shapes() -> None:
    text = (
        "연락처 010.1234.5678 또는 010 9876 5432\n식별값 9913329123456\n이메일 person@example.com"
    )

    masked = mask_qa_pii(text)

    for value in (
        "010.1234.5678",
        "010 9876 5432",
        "9913329123456",
        "person@example.com",
    ):
        assert value not in masked
    assert masked.count("[전화번호]") == 2
    assert "******-*******" in masked
    assert "[이메일]" in masked
