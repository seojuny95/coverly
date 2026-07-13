from collections.abc import Callable

import pytest

from app.services.pipeline import EmptyTextError, run_pipeline
from app.services.types import Coverage, ParsedDocument, PolicySummary, Table


def _fake_parse(text: str, tables: tuple[Table, ...] = ()) -> Callable[[bytes], ParsedDocument]:
    return lambda _bytes: ParsedDocument(text=text, layout_text=text, tables=tables)


def test_empty_text_raises() -> None:
    def fake_summarize(text: str) -> PolicySummary:
        return {"보험분류": "", "상품태그": []}

    def fake_extract(
        doc: ParsedDocument,
    ) -> tuple[list[Coverage], str]:
        return [], "완료"

    with pytest.raises(EmptyTextError):
        run_pipeline(
            b"%PDF-x",
            parse=_fake_parse(""),
            summarize=fake_summarize,
            extract=fake_extract,
        )


def test_auto_policy_is_not_skipped() -> None:
    # 자동차 분류여도 보장추출을 호출한다(스킵 없음).
    calls: list[str] = []

    def extract(doc: ParsedDocument) -> tuple[list[Coverage], str]:
        calls.append("extract")
        return [], "완료"

    def fake_summarize(text: str) -> PolicySummary:
        return {"보험분류": "자동차", "상품태그": []}

    result = run_pipeline(
        b"%PDF-x",
        parse=_fake_parse("자동차보험 증권 내용"),
        summarize=fake_summarize,
        extract=extract,
    )
    assert calls == ["extract"]  # 자동차도 추출을 시도
    assert result["분석상태"] in {"완료", "부분"}
    assert result["기본정보"]["보험분류"] == "자동차"


def test_result_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_summarize(text: str) -> PolicySummary:
        return {"보험분류": "실손", "상품태그": []}

    def fake_extract(
        doc: ParsedDocument,
    ) -> tuple[list[Coverage], str]:
        return [], "완료"

    result = run_pipeline(
        b"%PDF-x",
        parse=_fake_parse("일반 증권"),
        summarize=fake_summarize,
        extract=fake_extract,
        index=lambda _doc: "session-1",
    )
    assert set(result) == {"기본정보", "보장목록", "분석상태", "문자수", "문서세션ID"}
    assert result["문서세션ID"] == "session-1"
