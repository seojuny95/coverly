from app.services.session_rag import SessionRagStore


def test_session_rag_retrieves_uploaded_policy_text_and_masks_pii() -> None:
    store = SessionRagStore(ttl_seconds=60)
    session_id = store.add_text(
        "피보험자 가나 010-0000-0000\n암진단비 지급사유는 암 진단 확정입니다.",
        now=100.0,
    )

    assert session_id is not None
    hits = store.retrieve([session_id], "암진단비 지급사유", now=110.0)

    assert hits
    assert "암진단비" in hits[0].chunk.text
    assert "010-0000-0000" not in hits[0].chunk.text
    assert "[전화번호]" in hits[0].chunk.text


def test_session_rag_deletes_and_expires_sessions() -> None:
    store = SessionRagStore(ttl_seconds=10)
    session_id = store.add_text("후유장해 담보 원문", now=100.0)

    assert session_id is not None
    assert store.retrieve([session_id], "후유장해", now=105.0)
    assert store.retrieve([session_id], "후유장해", now=111.0) == []

    second_id = store.add_text("수술비 담보 원문", now=200.0)
    assert second_id is not None
    store.delete(second_id)
    assert store.retrieve([second_id], "수술비", now=201.0) == []
