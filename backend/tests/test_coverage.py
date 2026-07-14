"""Coverage extraction over a ParsedDocument: source building, LLM normalization,
grounding demotion, explanation fill, and failure degradation.

Unit tests inject fake completers/explainers (no real LLM). The real-sample
source-building tests run only when the gitignored sample PDFs are present —
they exercise pdfplumber table detection on real documents, not synthetic rows.
"""

import pytest

from app.services.policy.coverage import service as coverage_module
from app.services.policy.coverage.service import (
    STATUS_OK,
    STATUS_PARTIAL,
    build_coverage_source,
    extract_coverages,
    normalize_coverages,
    normalize_table_coverages,
)
from app.services.policy.models import Coverage, ParsedDocument, Table
from app.services.policy.parsing import parse_document
from tests.summary_helpers import SAMPLE_PDF_DIR

# ---------------------------------------------------------------------------
# Helpers

ADULT_BIRTH = "95" + "0524"

COVERAGE_TABLE: Table = (
    ("보장명", "보장상세", "가입금액"),
    ("암진단비(감액없음)", "암 진단 확정 시 최초 1회 지급", "30,000,000원"),
    ("교통사고처리지원금", "", "50,000,000원"),
)

SOURCE = (
    "| 보장명 | 보장상세 | 가입금액 |\n"
    "| --- | --- | --- |\n"
    "| 암진단비(감액없음) | 암 진단 확정 시 최초 1회 지급 | 30,000,000원 |\n"
    "| 교통사고처리지원금 |  | 50,000,000원 |"
)


def _doc(
    *,
    text: str = "",
    layout_text: str = "",
    tables: tuple[Table, ...] = (),
) -> ParsedDocument:
    return ParsedDocument(text=text, layout_text=layout_text, tables=tables)


def _coverage(name: str, detail: str | None) -> Coverage:
    return {"담보명": name, "가입금액": "1,000원", "보장내용": detail, "해설": None}


# ---------------------------------------------------------------------------
# build_coverage_source (tiered detection over an already-parsed document)


def test_coverage_table_is_serialized_as_markdown() -> None:
    source = build_coverage_source(_doc(tables=(COVERAGE_TABLE,)))

    assert source.startswith("| 보장명 |")
    assert "암진단비(감액없음)" in source
    assert "30,000,000원" in source


def test_non_coverage_tables_fall_back_to_layout_text() -> None:
    # No table carries coverage headers -> tier 3: every table + layout text.
    plain_table: Table = (("발행일", "지점"), ("2026-01-01", "강남"))
    doc = _doc(layout_text="가입담보 암진단비 3,000만원", tables=(plain_table,))

    source = build_coverage_source(doc)

    assert "가입담보 암진단비 3,000만원" in source
    assert "발행일" in source  # the unmatched table is still handed to the LLM


def test_empty_document_builds_empty_source() -> None:
    assert build_coverage_source(_doc()) == ""


def test_source_is_capped_to_the_max_length(monkeypatch: pytest.MonkeyPatch) -> None:
    # The tier-3 fallback can dump every page's layout text, so the source fed to
    # the LLM must be bounded — a large PDF must not blow up model input and cost.
    monkeypatch.setattr(coverage_module, "_MAX_SOURCE_CHARS", 10)

    source = build_coverage_source(_doc(layout_text="가나다라마바사아자차카타파하"))

    assert len(source) == 10


# ---------------------------------------------------------------------------
# normalize_coverages (structured LLM call + grounding)


def test_normalize_requests_and_keeps_the_verbatim_coverage_name() -> None:
    captured: dict[str, str] = {}

    def fake_complete(system: str, user: str) -> dict[str, object]:
        captured["system"] = system
        return {
            "보장목록": [
                {
                    "담보명": "암진단비(감액없음)",
                    "보장내용": "암 진단 확정 시 최초 1회 지급",
                    "가입금액": "30,000,000원",
                }
            ]
        }

    result = normalize_coverages(SOURCE, complete=fake_complete)

    assert "증권 표기 그대로" in captured["system"]
    assert result[0]["담보명"] == "암진단비(감액없음)"


def test_normalize_table_coverages_handles_clear_markdown_without_llm() -> None:
    result = normalize_table_coverages(SOURCE)

    assert result == [
        {
            "담보명": "암진단비(감액없음)",
            "가입금액": "30,000,000원",
            "보장내용": "암 진단 확정 시 최초 1회 지급",
            "해설": None,
        },
        {
            "담보명": "교통사고처리지원금",
            "가입금액": "50,000,000원",
            "보장내용": None,
            "해설": None,
        },
    ]


def test_normalize_table_coverages_finds_header_after_title_row() -> None:
    source = (
        "|  | 담보정보 |  |  |\n"
        "| --- | --- | --- | --- |\n"
        "| 가입담보 | 보장상세(지급조건) | 보험가입금액 | 보험기간/납입기간 |\n"
        "| 가족화재벌금(실손) | 벌금형 확정시 실제 납부한 벌금액 보상 | 2,000 만원 | 20년 |\n"
    )

    result = normalize_table_coverages(source)

    assert result == [
        {
            "담보명": "가족화재벌금(실손)",
            "가입금액": "2,000 만원",
            "보장내용": "벌금형 확정시 실제 납부한 벌금액 보상",
            "해설": None,
        }
    ]


def test_normalize_table_coverages_handles_content_column_as_name_with_wrapped_detail() -> None:
    source = (
        "| 구분 | 보장내용 | 납입/보험기간 | 가입금액 |\n"
        "| --- | --- | --- | --- |\n"
        "| 기본 | 일반상해후유장해(80%이상) | 20년납 100세만기 | 1,000만원 |\n"
        "|  | 보험기간 중 상해로 후유장해 상태가 된 경우 금액 지급 |  |  |\n"
        "| 선택 | 질병후유장해(3~100%)(감액없음) | 20년납 80세만기 | 3,000만원 |\n"
        "|  | 보험기간 중 질병으로 후유장해 상태가 된 경우 금액 지급 |  |  |\n"
    )

    result = normalize_table_coverages(source)

    assert result == [
        {
            "담보명": "일반상해후유장해(80%이상)",
            "가입금액": "1,000만원",
            "보장내용": "보험기간 중 상해로 후유장해 상태가 된 경우 금액 지급",
            "해설": None,
        },
        {
            "담보명": "질병후유장해(3~100%)(감액없음)",
            "가입금액": "3,000만원",
            "보장내용": "보험기간 중 질병으로 후유장해 상태가 된 경우 금액 지급",
            "해설": None,
        },
    ]


def test_normalize_drops_policy_wording_absent_from_source() -> None:
    # The LLM returned 보장내용 that does not appear in the source — a paraphrase or
    # hallucination. It must not be shown as authoritative 증권 원문; drop it to None
    # so the coverage falls through to a clearly-labeled generated 해설 downstream.
    def fake_complete(system: str, user: str) -> dict[str, object]:
        return {
            "보장목록": [
                {
                    "담보명": "암진단비",
                    "보장내용": "모든 암에 무조건 1억원을 지급",
                    "가입금액": "30,000,000원",
                }
            ]
        }

    result = normalize_coverages(SOURCE, complete=fake_complete)

    assert result[0]["보장내용"] is None


def test_normalize_keeps_policy_wording_present_in_source() -> None:
    # Verbatim wording (whitespace aside) grounds and is kept as authoritative.
    def fake_complete(system: str, user: str) -> dict[str, object]:
        return {
            "보장목록": [
                {
                    "담보명": "암진단비",
                    "보장내용": "암 진단 확정 시 최초 1회 지급",
                    "가입금액": "30,000,000원",
                }
            ]
        }

    result = normalize_coverages(SOURCE, complete=fake_complete)

    assert result[0]["보장내용"] == "암 진단 확정 시 최초 1회 지급"


def test_normalize_maps_rows_into_coverages() -> None:
    def fake_complete(system: str, user: str) -> dict[str, object]:
        return {
            "보장목록": [
                {
                    "담보명": "암진단비",
                    "보장내용": "암 진단 확정 시 최초 1회 지급",
                    "가입금액": "30,000,000원",
                },
                {"담보명": "교통사고처리지원금", "보장내용": None, "가입금액": "50,000,000원"},
            ]
        }

    result = normalize_coverages(SOURCE, complete=fake_complete)

    assert result == [
        {
            "담보명": "암진단비",
            "가입금액": "30,000,000원",
            "보장내용": "암 진단 확정 시 최초 1회 지급",
            "해설": None,
        },
        {
            "담보명": "교통사고처리지원금",
            "가입금액": "50,000,000원",
            "보장내용": None,
            "해설": None,
        },
    ]


def test_normalize_masks_identifier_before_llm_without_weakening_grounding() -> None:
    raw_identifier = f"{ADULT_BIRTH}-1******"
    source = f"피보험자 {raw_identifier}\n{SOURCE}"
    captured: dict[str, str] = {}

    def fake_complete(system: str, user: str) -> dict[str, object]:
        captured["user"] = user
        return {
            "보장목록": [
                {
                    "담보명": "암진단비",
                    "보장내용": "암 진단 확정 시 최초 1회 지급",
                    "가입금액": "30,000,000원",
                }
            ]
        }

    result = normalize_coverages(source, complete=fake_complete)

    assert raw_identifier not in captured["user"]
    assert ADULT_BIRTH not in captured["user"]
    assert "******-*******" in captured["user"]
    assert result[0]["보장내용"] == "암 진단 확정 시 최초 1회 지급"


def test_normalize_demotes_hallucinated_amounts() -> None:
    def fake_complete(system: str, user: str) -> dict[str, object]:
        return {
            "보장목록": [
                {"담보명": "암진단비", "보장내용": None, "가입금액": "77,777,777원"},
            ]
        }

    result = normalize_coverages(SOURCE, complete=fake_complete)

    assert result[0]["가입금액"] == "확인필요"


def test_normalize_skips_invalid_rows() -> None:
    def fake_complete(system: str, user: str) -> dict[str, object]:
        return {
            "보장목록": [
                {"보장내용": "담보명이 없는 행", "가입금액": "1,000원"},
                {"담보명": "정상담보", "보장내용": None, "가입금액": ""},
                "행이 아님",
            ]
        }

    result = normalize_coverages(SOURCE, complete=fake_complete)

    assert [coverage["담보명"] for coverage in result] == ["정상담보"]
    assert result[0]["가입금액"] == "확인필요"  # empty cell -> nothing to show


def test_normalize_drops_wording_that_merely_repeats_the_amount() -> None:
    # Auto tables have no 보장내용 column, so the LLM copies the limit phrase
    # into both fields. A wording identical to the amount (whitespace aside)
    # describes the amount, not the coverage — drop it to None so the
    # explanation pass can say what the coverage actually covers.
    def fake_complete(system: str, user: str) -> dict[str, object]:
        return {
            "보장목록": [
                {
                    "담보명": "대인배상Ⅱ",
                    "보장내용": "1인당 무 한",
                    "가입금액": "1인당 무한",
                    "유형": "담보",
                },
                {
                    "담보명": "암진단비",
                    "보장내용": "암 진단 확정 시 최초 1회 지급",
                    "가입금액": "30,000,000원",
                },
            ]
        }

    source = "| 담보종목 |  |\n| --- | --- |\n| 대인배상Ⅱ | 1인당 무 한 |\n" + SOURCE
    result = normalize_coverages(source, complete=fake_complete)

    assert result[0]["보장내용"] is None  # duplicate of the amount → dropped
    assert result[0]["가입금액"] == "1인당 무한"
    assert result[1]["보장내용"] == "암 진단 확정 시 최초 1회 지급"  # real wording kept


def test_normalize_recovers_amount_from_titled_amount_column() -> None:
    # The LLM sometimes files the amount cell under 보장내용 and leaves 가입금액
    # empty. The table structure is authoritative — the amount is recovered from
    # the column whose header names an amount, and the duplicated wording is
    # dropped so the explanation pass can fill 해설.
    def fake_complete(system: str, user: str) -> dict[str, object]:
        return {
            "보장목록": [
                {
                    "담보명": "대인배상Ⅰ",
                    "보장내용": "자배법에서 정한 금액",
                    "가입금액": "",
                    "유형": "담보",
                }
            ]
        }

    source = "| 담보종목 | 보험가입금액 |\n| --- | --- |\n| 대인배상Ⅰ | 자배법에서 정한 금액 |"
    result = normalize_coverages(source, complete=fake_complete)

    assert result[0]["가입금액"] == "자배법에서 정한 금액"  # recovered from the table
    assert result[0]["보장내용"] is None  # duplicate of the amount → 해설 대상


def test_normalize_never_recovers_from_a_titled_description_column() -> None:
    # Recovery must not stuff a description into the amount: when the adjacent
    # column has a non-amount title (보장상세), there is nothing to recover —
    # the missing amount stays a verification gap (확인필요).
    def fake_complete(system: str, user: str) -> dict[str, object]:
        return {"보장목록": [{"담보명": "암진단비", "보장내용": None, "가입금액": ""}]}

    source = "| 담보명 | 보장상세 |\n| --- | --- |\n| 암진단비 | 암 진단 확정 시 지급 |"
    result = normalize_coverages(source, complete=fake_complete)

    assert result[0]["가입금액"] == "확인필요"


def test_normalize_recovers_amount_from_untitled_adjacent_column() -> None:
    # Auto-style tables print the limit in an untitled cell right next to the
    # name. An untitled adjacent column is safe to recover from — it cannot be
    # a description column (those carry a header).
    def fake_complete(system: str, user: str) -> dict[str, object]:
        return {
            "보장목록": [{"담보명": "대인배상Ⅰ", "보장내용": None, "가입금액": "", "유형": "담보"}]
        }

    source = "| 담보종목 |  |\n| --- | --- |\n| 대인배상Ⅰ | 자배법에서 정한 금액 |"
    result = normalize_coverages(source, complete=fake_complete)

    assert result[0]["가입금액"] == "자배법에서 정한 금액"


def test_normalize_recovers_amount_from_continuation_row() -> None:
    # pdfplumber sometimes wraps the amount onto a continuation row (empty name
    # cell, value in the adjacent cell) — recovery looks one row ahead.
    def fake_complete(system: str, user: str) -> dict[str, object]:
        return {
            "보장목록": [
                {"담보명": "긴급출동특약", "보장내용": None, "가입금액": "", "유형": "부가"}
            ]
        }

    source = (
        "| 담보종목 |  |\n| --- | --- |\n"
        "| 긴급출동특약 |  |\n"
        "|  | 하이카서비스 총 6회 (견인 100km한도) |"
    )
    result = normalize_coverages(source, complete=fake_complete)

    assert result[0]["가입금액"] == "하이카서비스 총 6회 (견인 100km한도)"
    # A row with its own amount cell is a coverage, whatever the LLM called it.
    assert result[0].get("유형", "담보") == "담보"


def test_normalize_keeps_rider_amount_empty_not_unverified() -> None:
    # 부가 rows are name-only: an empty amount is their expected shape, so it
    # must stay "" instead of being demoted to 확인필요 (which would imply an
    # amount exists but could not be verified).
    def fake_complete(system: str, user: str) -> dict[str, object]:
        return {
            "보장목록": [
                {"담보명": "안전운전할인특약", "보장내용": None, "가입금액": "", "유형": "부가"},
                {"담보명": "대인배상Ⅰ", "보장내용": None, "가입금액": "", "유형": "담보"},
            ]
        }

    result = normalize_coverages("대인배상Ⅰ 안전운전할인특약", complete=fake_complete)

    assert result[0]["가입금액"] == ""  # rider: empty stays empty
    assert result[1]["가입금액"] == "확인필요"  # core: empty is a verification gap


def test_normalize_returns_no_coverages_for_blank_source() -> None:
    # Even if the model would return rows, a blank source has no coverages to show.
    def fake_complete(system: str, user: str) -> dict[str, object]:
        return {"보장목록": [{"담보명": "지어낸담보", "보장내용": None, "가입금액": "1원"}]}

    assert normalize_coverages("   ", complete=fake_complete) == []


def test_prompt_carries_structural_type_rules_for_every_policy() -> None:
    # One prompt for all policies: the structural 담보/부가 rules are not
    # category-gated — an unfriendly non-auto policy gets them too.
    captured: dict[str, str] = {}

    def fake_complete(system: str, user: str) -> dict[str, object]:
        captured["system"] = system
        return {"보장목록": []}

    normalize_coverages(
        "| 담보명 | 가입금액 |\n| --- | --- |\n| 암진단비 | 1억원 |",
        complete=fake_complete,
    )
    assert "부가" in captured["system"]
    assert "담보" in captured["system"]


def test_normalize_carries_유형_from_llm() -> None:
    def fake_complete(system: str, user: str) -> dict[str, object]:
        return {
            "보장목록": [
                {"담보명": "대인배상Ⅰ", "보장내용": None, "가입금액": "무한", "유형": "담보"},
                {"담보명": "안전운전할인특약", "보장내용": None, "가입금액": "", "유형": "부가"},
            ]
        }

    result = normalize_coverages("대인배상Ⅰ 무한 안전운전할인특약", complete=fake_complete)
    assert result[0].get("유형", "담보") == "담보"
    assert result[1]["유형"] == "부가"


def test_extract_skips_explanation_for_부가_rows() -> None:
    explained: list[str] = []

    def fake_explain(names: list[str]) -> tuple[dict[str, str], bool]:
        explained.extend(names)
        return {name: "설명" for name in names}, True

    rows: list[Coverage] = [
        {"담보명": "대인배상Ⅰ", "가입금액": "무한", "보장내용": None, "해설": None, "유형": "담보"},
        {
            "담보명": "안전운전할인특약",
            "가입금액": "",
            "보장내용": None,
            "해설": None,
            "유형": "부가",
        },
    ]
    coverages, status = extract_coverages(
        _doc(tables=(COVERAGE_TABLE,)), normalize=lambda _s: rows, explain=fake_explain
    )
    assert explained == ["대인배상Ⅰ"]
    assert coverages[1]["해설"] is None
    assert status == STATUS_OK


# ---------------------------------------------------------------------------
# extract_coverages (orchestrator: never raises, degrades to 부분)


def test_empty_document_is_a_clean_empty_result() -> None:
    coverages, status = extract_coverages(_doc(), normalize=lambda _s: [])

    assert coverages == []
    assert status == STATUS_OK


def test_partial_when_source_is_nonempty_but_yields_no_coverages() -> None:
    # A non-empty source we could not turn into any coverage (empty structured
    # output, or every row failing validation) is a silent extraction failure —
    # surface it as 부분 so the UI does not show it as a clean empty result.
    coverages, status = extract_coverages(_doc(tables=(COVERAGE_TABLE,)), normalize=lambda _s: [])

    assert coverages == []
    assert status == STATUS_PARTIAL


def test_generates_explanation_for_coverage_missing_policy_wording() -> None:
    def fake_explain(names: list[str]) -> tuple[dict[str, str], bool]:
        return {name: f"{name} 설명이에요." for name in names}, True

    coverages, status = extract_coverages(
        _doc(tables=(COVERAGE_TABLE,)),
        normalize=lambda _s: [_coverage("교통사고처리지원금", None)],
        explain=fake_explain,
    )

    assert status == STATUS_OK
    assert coverages[0]["해설"] == "교통사고처리지원금 설명이에요."


def test_default_extract_generates_missing_explanations_without_external_calls() -> None:
    coverages, status = extract_coverages(
        _doc(tables=(COVERAGE_TABLE,)),
        normalize=lambda _s: [_coverage("교통사고처리지원금", None)],
    )

    assert status == STATUS_OK
    assert coverages[0]["해설"]


def test_policy_wording_is_not_overwritten_by_generated_explanation() -> None:
    # An explanation is offered for every name, but a coverage that already has
    # policy wording must keep it — 해설 stays None (증권 원문 우선).
    def fake_explain(names: list[str]) -> tuple[dict[str, str], bool]:
        return {name: "지어낸 설명" for name in names}, True

    coverages, status = extract_coverages(
        _doc(tables=(COVERAGE_TABLE,)),
        normalize=lambda _s: [
            _coverage("암진단비", "암 진단 시 지급"),
            _coverage("교통사고처리지원금", None),
        ],
        explain=fake_explain,
    )

    assert status == STATUS_OK
    assert coverages[0]["보장내용"] == "암 진단 시 지급"
    assert coverages[0]["해설"] is None
    assert coverages[1]["해설"] == "지어낸 설명"


def test_partial_when_explanations_fail() -> None:
    coverages, status = extract_coverages(
        _doc(tables=(COVERAGE_TABLE,)),
        normalize=lambda _s: [_coverage("암진단비", None)],
        explain=lambda _names: ({}, False),
    )

    assert status == STATUS_PARTIAL
    assert coverages[0]["담보명"] == "암진단비"  # coverages are still returned
    assert coverages[0]["해설"] is None


def test_degrades_to_empty_partial_when_normalization_raises() -> None:
    def failing_normalize(_source: str) -> list[Coverage]:
        raise RuntimeError("LLM down")

    coverages, status = extract_coverages(
        _doc(tables=(COVERAGE_TABLE,)), normalize=failing_normalize
    )

    assert coverages == []
    assert status == STATUS_PARTIAL


# ---------------------------------------------------------------------------
# Real-sample source building (pdfplumber on real documents; no LLM calls)

_SAMPLES_AVAILABLE = SAMPLE_PDF_DIR.exists()

SAMPLE_FILENAMES = [
    "DB운전자보험증권.pdf",
    "NH농협보험증권.pdf",
    "현대해상자동차보험.pdf",
    "흥국보험증권.pdf",
]

_AMOUNT_HEADERS = ("가입금액", "보험가입금액", "보장금액", "보험금액", "한도")


@pytest.mark.skipif(not _SAMPLES_AVAILABLE, reason="local sample PDFs are not available")
@pytest.mark.parametrize("filename", SAMPLE_FILENAMES)
def test_extracts_markdown_coverage_source_from_real_policy(filename: str) -> None:
    doc = parse_document((SAMPLE_PDF_DIR / filename).read_bytes())
    source = build_coverage_source(doc)

    # A coverage table was detected and serialized as markdown (starts with a row),
    # and it carries an amount column — i.e. it is the coverage table, not prose.
    assert source.startswith("| "), f"{filename}: no markdown coverage table detected"
    assert any(header in source for header in _AMOUNT_HEADERS), (
        f"{filename}: detected table has no amount column"
    )


@pytest.mark.skipif(not _SAMPLES_AVAILABLE, reason="local sample PDFs are not available")
def test_wrapped_cell_lines_rejoined_with_a_space_not_merged_or_slashed() -> None:
    # NH cells wrap across visual lines (e.g. "수술을\n받은 경우"). Rejoin with a
    # space so distinct words are not merged ("수술을받은"), and never with the old
    # " / " marker, which leaked into 보장내용 as a stray slash. Only "\n" is
    # rewritten, so a genuine "/" in the policy text is never touched.
    doc = parse_document((SAMPLE_PDF_DIR / "NH농협보험증권.pdf").read_bytes())
    source = build_coverage_source(doc)

    assert "수술을 받은" in source
    assert "수술을받은" not in source
    assert " / " not in source
