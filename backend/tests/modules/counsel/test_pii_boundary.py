from app.modules.counsel.pii import mask_counsel_pii, masked_history
from app.modules.counsel.schemas import CounselMessage


def test_user_typed_identifiers_never_reach_the_model() -> None:
    # The question is client text. qa masked it before the model boundary and the
    # rule outlived qa: anything sent to OpenAI is also what tracing would export.
    masked = mask_counsel_pii(
        "제 주민번호는 900101-1234567이고 010-1234-5678로 연락주세요. a@b.com"
    )

    assert "900101-1234567" not in masked
    assert "010-1234-5678" not in masked
    assert "a@b.com" not in masked


def test_masking_leaves_the_insurance_question_intact() -> None:
    assert mask_counsel_pii("암진단비(유사암제외) 얼마야?") == "암진단비(유사암제외) 얼마야?"


def test_history_is_masked_turn_by_turn() -> None:
    history = [
        CounselMessage(role="user", content="010-1234-5678 입니다"),
        CounselMessage(role="assistant", content="네, 확인했어요"),
    ]

    masked = masked_history(history)

    assert "010-1234-5678" not in masked[0].content
    assert masked[0].role == "user"
    assert masked[1].content == "네, 확인했어요"
