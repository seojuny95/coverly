"""Coverage (담보) extraction over an already-parsed document.

Source building is tiered because the failure costs are asymmetric — a missed
table loses the whole coverage list, while a spurious one only adds a few
prompt tokens the LLM is told to ignore:

1. strict: a table whose cells contain both a name header and an amount header
2. relaxed: name header only (unusual amount column labels)
3. fallback: no match at all -> every table as markdown + layout text, so the
   worst case equals the no-detection baseline

Insurers print the coverage table with different columns; one structured-output
LLM call maps any layout into the same fields. Everything the LLM returns is
grounded against the source before we present it as authoritative 증권 원문
(see app.services.grounding): amounts are demoted to 확인필요 and 보장내용 that
does not appear in the source is dropped to None, so the coverage falls through
to a clearly-labeled generated 해설 instead of a paraphrase shown as the
policy's own wording.

extract_coverages never raises (failure isolation lives here so callers stay
thin): any error in normalization degrades to an empty list + 부분, and an
explanation failure keeps the extracted coverages (해설 stays None).
"""

import re
from collections.abc import Callable
from functools import lru_cache, partial
from typing import Literal

from pydantic import BaseModel, ValidationError

from app.services.explain import explain_coverages
from app.services.grounding import normalize_amount, wording_grounded
from app.services.llm import JsonCompleter, structured_completer
from app.services.types import Coverage, ParsedDocument

STATUS_OK = "완료"
STATUS_PARTIAL = "부분"

Normalizer = Callable[[str], list[Coverage]]
Explainer = Callable[[list[str]], tuple[dict[str, str], bool]]

_TableRows = list[list[str | None]]

# Upper bound on the source handed to the LLM. The tier-3 fallback can dump every
# page's layout text, so cap it to bound model input and cost on large PDFs.
_MAX_SOURCE_CHARS = 30_000

# Header vocabulary observed across sample policies, kept intentionally wider
# than the samples so unseen insurers still match tier 1.
_NAME_HEADERS = ("보장명", "담보명", "담보종목", "보장상세", "특약명")
_AMOUNT_HEADERS = ("가입금액", "보험가입금액", "보장금액", "보험금액", "한도")

_SYSTEM = (
    "너는 보험 증권의 담보(보장) 표를 통일된 형식으로 정리하는 도우미다. "
    "입력은 증권에서 추출한 담보표 마크다운(또는 레이아웃 텍스트)이다. "
    "열 제목(보장명·담보명·담보종목·보장상세·보장내용·가입금액 등)을 보고 각 값을 정확히 매핑하라. "
    "표에 실제로 있는 담보만 옮기고 새로 지어내지 마라. "
    "담보명은 증권 표기를 살리되, 보장 대상·사고를 바꾸지 않는 순수 수식어는 "
    "괄호 안이라도 제거한다 "
    "— '감액없음'·'감액'·'기본계약'·'주계약'·'선택'·'무배당' 같은 지급방식·계약형태 표시. "
    "예: '암진단비(유사암제외)(감액없음)'→'암진단비(유사암제외)'. "
    "'기본계약(일반상해후유장해(80%이상))'처럼 담보명을 감싸는 접두 래퍼는 바깥 래퍼만 벗긴다. "
    "반대로 '유사암제외'·'80%이상'·'1~5종'처럼 보장 범위·지급조건을 가르는 수식어는 반드시 남긴다. "
    "보장내용은 증권 원문 그대로 옮긴다(요약·축약 금지, '※'로 시작하는 단서 포함). 없으면 null. "
    "가입금액이 없으면 빈 문자열로 둔다. "
    "유형은 항상 '담보'로 표시한다."
)

# Appended to _SYSTEM only for 자동차 policies — their coverage tables mix real
# coverages with rate/discount riders and section headers, which the default
# prompt has no vocabulary for.
_AUTO_GUIDANCE = (
    "이 증권은 자동차보험이다. 다음 지침을 추가로 따른다: "
    "금액·한도 칸의 문구는 요약하지 말고 그대로 가입금액에 옮긴다 "
    "('1인당 무한', '자배법에서 정한 금액'처럼 한도를 서술하는 문구도 포함). "
    "여러 담보를 묶는 섹션·그룹 표제(예: '대인배상', '기본계약')는 담보 자체가 아니므로 "
    "별도 행으로 만들지 마라. "
    "보험료 할인·서비스·요율·기타 부가 특약은 이름만 정확히 옮기고 유형을 '부가'로 표시한다. "
    "대인배상·대물배상·자기신체사고·자기차량손해 등 실제 보장 담보는 유형을 '담보'로 표시한다."
)


# ---------------------------------------------------------------------------
# Source building: tiered table selection + markdown serialization


def _flatten(rows: _TableRows) -> str:
    cells: list[str] = []
    for row in rows:
        for cell in row:
            cells.append(cell or "")
    return " ".join(cells)


def _is_coverage_table(rows: _TableRows, *, require_amount: bool = True) -> bool:
    """True when the table's cells carry coverage headers (merged title rows OK)."""
    flat = _flatten(rows)
    if not any(header in flat for header in _NAME_HEADERS):
        return False
    return not require_amount or any(header in flat for header in _AMOUNT_HEADERS)


def _select_coverage_tables(tables: list[_TableRows]) -> list[_TableRows]:
    """Coverage tables by tiered matching: strict (name+amount) first, then name-only."""
    strict = [table for table in tables if _is_coverage_table(table)]
    if strict:
        return strict
    return [table for table in tables if _is_coverage_table(table, require_amount=False)]


def _join_cell_lines(cell: str) -> str:
    """Rejoin a cell that pdfplumber split across visual lines.

    A markdown cell must be one line, so cell-internal newlines are rejoined with
    a single space. pdfplumber drops the wrap space inconsistently and a mid-word
    wrap ('한'+'하여') is indistinguishable from a word-boundary wrap
    ('수술을'+'받은'), so a space is the safe default: it never merges distinct
    words (a rare mid-word wrap only gains a harmless space). This replaces the
    old ' / ' marker, which leaked into 보장내용 as a stray slash the reader could
    not tell apart from a real '/'. Only whitespace is rewritten, so a genuine
    '/' in the policy text is untouched.
    """
    return re.sub(r"\s+", " ", cell.replace("\n", " ")).strip()


def _serialize_table(rows: _TableRows) -> str:
    """Render a table as markdown so column-row associations survive.

    Cell-internal line wraps are rejoined (see _join_cell_lines). Returns '' for
    non-tables (<2 rows or <2 columns).
    """
    clean = [[_join_cell_lines(cell or "") for cell in row] for row in rows]
    clean = [row for row in clean if any(row)]
    if len(clean) < 2 or len(clean[0]) < 2:
        return ""
    width = len(clean[0])
    lines = [
        "| " + " | ".join(clean[0]) + " |",
        "| " + " | ".join(["---"] * width) + " |",
    ]
    for row in clean[1:]:
        cells = (row + [""] * width)[:width]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def build_coverage_source(doc: ParsedDocument) -> str:
    """LLM input for coverage extraction, via the tiered detection above."""
    tables: list[_TableRows] = []
    for table in doc.tables:
        tables.append([list(row) for row in table])

    selected = _select_coverage_tables(tables)
    if selected:
        source = "\n\n".join(md for table in selected if (md := _serialize_table(table)))
    else:
        # Tier 3: no coverage table detected — hand the LLM everything we have.
        parts = [md for table in tables if (md := _serialize_table(table))]
        if doc.layout_text:
            parts.append(doc.layout_text)
        source = "\n".join(parts).strip()
    return source[:_MAX_SOURCE_CHARS]


# ---------------------------------------------------------------------------
# LLM normalization: any column layout -> the unified Coverage shape


class _CoverageRow(BaseModel):
    담보명: str
    보장내용: str | None
    가입금액: str
    유형: Literal["담보", "부가"] = "담보"


class _CoverageList(BaseModel):
    보장목록: list[_CoverageRow]


@lru_cache
def _default_completer() -> JsonCompleter:
    return structured_completer(_CoverageList)


def normalize_coverages(
    source: str, category: str | None = None, complete: JsonCompleter | None = None
) -> list[Coverage]:
    """Map a coverage-table source into Coverages (one structured LLM call)."""
    if not source.strip():
        return []
    completer = complete or _default_completer()
    system = _SYSTEM + _AUTO_GUIDANCE if category == "자동차" else _SYSTEM
    rows = completer(system, source).get("보장목록", [])
    if not isinstance(rows, list):
        return []

    coverages: list[Coverage] = []
    for row in rows:
        try:
            parsed = _CoverageRow.model_validate(row)
        except ValidationError:
            continue
        detail = parsed.보장내용.strip() if parsed.보장내용 else None
        if detail and not wording_grounded(detail, source):
            detail = None  # not the policy's own wording — don't present it as 원문
        coverage = Coverage(
            담보명=parsed.담보명.strip(),
            가입금액=normalize_amount(parsed.가입금액, source),
            보장내용=detail or None,
            해설=None,
        )
        if parsed.유형 != "담보":
            coverage["유형"] = parsed.유형  # omit for 담보 rows — preserve response shape
        coverages.append(coverage)
    return coverages


# ---------------------------------------------------------------------------
# Orchestrator


def _needs_explanation(coverage: Coverage) -> bool:
    """Only 담보 rows without policy wording get a generated 해설 — 부가 rows are
    name-only riders/rates with nothing substantive to explain."""
    return not coverage["보장내용"] and coverage.get("유형", "담보") == "담보"


def extract_coverages(
    doc: ParsedDocument,
    *,
    category: str | None = None,
    normalize: Normalizer | None = None,
    explain: Explainer = explain_coverages,
) -> tuple[list[Coverage], str]:
    """Extract the coverage list from a parsed policy document, best-effort."""
    resolve_normalizer = normalize or partial(normalize_coverages, category=category)
    try:
        source = build_coverage_source(doc)
        coverages = resolve_normalizer(source)
    except Exception:
        return [], STATUS_PARTIAL

    if not coverages:
        # A non-empty source that produced no coverages (empty structured output
        # or every row failing validation) is a silent failure, not a clean empty
        # result — surface 부분. A blank source means there was nothing to analyze.
        return [], STATUS_PARTIAL if source.strip() else STATUS_OK

    missing = [c["담보명"] for c in coverages if _needs_explanation(c)]
    if not missing:
        return coverages, STATUS_OK

    explanations, ok = explain(missing)
    for coverage in coverages:
        if _needs_explanation(coverage):
            coverage["해설"] = explanations.get(coverage["담보명"])
    return coverages, STATUS_OK if ok else STATUS_PARTIAL
