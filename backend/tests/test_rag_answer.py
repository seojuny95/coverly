from pathlib import Path

from app.services.prompt_loader import load_prompt
from app.services.rag.official.answer import answer_official_question
from app.services.rag.official.models import RagChunk, RetrievalHit

_PROMPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "services"
    / "rag"
    / "official"
    / "rag_answer_prompt.md"
)


def _hit(chunk: RagChunk) -> RetrievalHit:
    return RetrievalHit(chunk=chunk, score=10.0, keyword_score=10.0, vector_score=1.0)


def _chunk(
    *,
    chunk_id: str = "chunk-1",
    text: str = "제2조(계약 전 알릴 의무) 계약자 또는 피보험자는 중요한 사항을 알려야 합니다.",
    label: str = "제2조(계약 전 알릴 의무)",
) -> RagChunk:
    return RagChunk(
        id=chunk_id,
        source_id="standard_terms_annex_15_2026_06_30",
        source_title="보험업감독업무시행세칙 별표15 표준약관",
        source_category="standard_clause",
        publisher="금융감독원",
        text=text,
        page_start=10,
        page_end=10,
        label=label,
        citation_label=f"표준약관 {label}",
        version_label="시행일 2026-06-30",
        source_url="https://www.law.go.kr/LSW/flDownload.do?flSeq=166365465",
    )


def test_answer_official_question_requires_valid_citation_id() -> None:
    result = answer_official_question(
        "계약 전 알릴 의무가 뭐야?",
        hits=[_hit(_chunk())],
        complete=lambda _system, _user: {
            "answer": "계약 전 알릴 의무는 중요한 사항을 보험사에 알려야 하는 의무예요.",
            "citation_ids": ["missing"],
            "missing_context": [],
        },
    )

    assert result.status == "filtered"
    assert result.missing_context == ("유효한 근거 인용 없음",)


def test_answer_official_question_returns_cited_term_explanation() -> None:
    result = answer_official_question(
        "계약 전 알릴 의무가 뭐야?",
        hits=[_hit(_chunk())],
        complete=lambda _system, _user: {
            "answer": "계약 전 알릴 의무는 가입 전에 중요한 사항을 알려야 한다는 뜻이에요.",
            "citation_ids": ["chunk-1"],
            "missing_context": [],
        },
    )

    assert result.status == "answered"
    assert result.mode == "general"
    assert result.citations[0].chunk_id == "chunk-1"
    assert "공식자료" in result.limitations[0]


def test_answer_official_question_keeps_missing_context() -> None:
    result = answer_official_question(
        "암 진단비 받을 수 있어?",
        hits=[
            _hit(
                _chunk(
                    text=(
                        "제3조(보험금의 지급사유) 회사는 약관에서 정한 "
                        "암 진단 확정 시 보험금을 지급합니다."
                    ),
                    label="제3조(보험금의 지급사유)",
                )
            )
        ],
        complete=lambda _system, _user: {
            "answer": "표준약관 기준으로는 지급사유와 진단확정 기준을 확인해야 해요.",
            "citation_ids": ["chunk-1"],
            "missing_context": ["가입 상품 약관", "진단일"],
        },
    )

    assert result.status == "answered"
    assert result.mode == "general"
    assert result.missing_context == ("가입 상품 약관", "진단일")


def test_answer_official_question_replaces_generic_missing_context() -> None:
    result = answer_official_question(
        "내 실손보험에서 도수치료가 보장돼?",
        hits=[_hit(_chunk())],
        complete=lambda _system, _user: {
            "answer": "제공된 공식자료만으로는 도수치료 보장 여부를 확인할 수 없어요.",
            "citation_ids": ["chunk-1"],
            "missing_context": ["개별 판단에 추가로 필요한 정보"],
        },
    )

    assert result.status == "answered"
    assert result.missing_context == ()


def test_answer_official_question_allows_grounded_payment_language() -> None:
    result = answer_official_question(
        "암 진단비 받을 수 있어?",
        hits=[_hit(_chunk(label="제3조(보험금의 지급사유)"))],
        complete=lambda _system, _user: {
            "answer": (
                "표준약관 기준으로 암 진단 확정이라는 지급사유에 해당하면 보험금이 지급됩니다."
            ),
            "citation_ids": ["chunk-1"],
            "missing_context": ["가입 상품 약관", "진단확정 서류"],
        },
    )

    assert result.status == "answered"
    assert "보험금이 지급됩니다" in result.answer


def test_answer_official_question_no_evidence_without_hits() -> None:
    result = answer_official_question("없는 질문", hits=[])

    assert result.status == "no_evidence"
    assert result.citations == ()


def test_rag_answer_prompt_has_required_sections() -> None:
    prompt = load_prompt(_PROMPT_PATH)

    assert "# 역할" in prompt
    assert "# 작업 순서" in prompt
    assert "# 하지 말아야 할 것" in prompt
    assert "# 부족한 정보" in prompt
    assert "# 출력 규칙" in prompt


def test_rag_answer_prompt_keeps_generation_eval_rules_visible() -> None:
    prompt = load_prompt(_PROMPT_PATH)

    assert "30일 초과 불가" in prompt
    assert "치료 기록" in prompt
    assert "위반 내용" in prompt
    assert "보험금 지급사유" in prompt
    assert "포괄 문구" in prompt
