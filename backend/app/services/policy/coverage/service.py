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
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, ValidationError

from app.services.grounding import normalize_amount, wording_grounded
from app.services.llm import JsonCompleter, structured_completer
from app.services.policy.coverage.explanation import explain_coverages_fast
from app.services.policy.demographics import mask_demographic_identifiers
from app.services.policy.models import Coverage, ParsedDocument
from app.services.table_text import serialize_table

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
_NAME_HEADERS = ("가입담보", "보장명", "담보명", "담보종목", "보장상세", "보장내용", "특약명")
_NAME_COLUMN_HEADERS = ("가입담보", "보장명", "담보명", "담보종목", "특약명")
_AMOUNT_HEADERS = ("가입금액", "보험가입금액", "보장금액", "보험금액", "한도")
_DETAIL_HEADERS = ("보장상세", "지급조건", "보장내용")
_SECTION_HEADER_NAMES = (
    "기본계약",
    "보험료할인특약",
    "보장확대및기타특약",
    "보장확대기타특약",
    "기타특약",
    "특별요율",
)
_NOTICE_NAME_MARKERS = (
    "보험금지급",
    "보상되지",
    "보상되지않",
    "알리지",
    "알려야",
    "청약서",
    "자필서명",
    "직업이나직무",
    "이륜자동차",
    "감액될수있",
    "거절되거나",
    "사실그대로",
)
_COVERAGE_NAME_MARKERS = (
    "보험",
    "특약",
    "담보",
    "배상",
    "손해",
    "상해",
    "질병",
    "진단",
    "수술",
    "입원",
    "후유장해",
    "벌금",
    "비용",
    "지원금",
)
_STRONG_COVERAGE_NAME_MARKERS = ("특약", "담보")
_DETAIL_SENTENCE_MARKERS = (
    "보험기간",
    "경우",
    "때",
    "하면",
    "한 경우",
    "된 경우",
    "받은 경우",
    "지급",
    "보상",
    "발생",
    "확정",
)

# One prompt for every policy type. The 담보/부가 split and the verbatim-amount
# rules are structural (driven by the table's shape), so an unfriendly non-auto
# policy that prints limits as prose or lists rider names gets the same handling
# as an auto policy.
_SYSTEM = (
    "너는 보험 증권의 담보(보장) 표를 통일된 형식으로 정리하는 도우미다. "
    "입력은 증권에서 추출한 담보표 마크다운(또는 레이아웃 텍스트)이다. "
    "열 제목(보장명·담보명·담보종목·보장상세·보장내용·가입금액 등)을 보고 각 값을 정확히 매핑하라. "
    "표에 실제로 있는 담보만 옮기고 새로 지어내지 마라. "
    "담보명은 증권 표기 그대로 옮긴다. "
    "괄호 안 수식어, 감액없음·유사암제외·80%이상·1~5종 같은 지급조건, "
    "기본계약·주계약·선택·무배당 같은 계약형태 표시도 임의로 제거하거나 고쳐 쓰지 마라. "
    "서로 다른 증권의 담보명 비교, 유사도 판단, "
    "화면 표시용 이름 정리는 후속 집계 단계에서 처리한다. "
    "보장내용은 증권 원문 그대로 옮긴다(요약·축약 금지, '※'로 시작하는 단서 포함). 없으면 null. "
    "금액·한도 칸의 문구는 아무리 길어도 설명이 아니라 가입금액이다 — 요약하지 말고 "
    "그대로 가입금액에 옮긴다 ('1인당 무한', '자배법에서 정한 금액'처럼 한도를 서술하는 "
    "문구도 포함). 금액 칸은 제목 없이 담보명 바로 옆에 올 수도 있다. "
    "한도 문구를 보장내용에 중복해 넣지 말고, 표에 별도의 보장 설명이 없으면 보장내용은 "
    "null로 둔다. 가입금액이 정말 없으면 빈 문자열로 둔다. "
    "유형은 이름의 의미가 아니라 표의 구조로 판정한다 — "
    "행에 금액·한도 칸 내용이 있으면(이름이 특약이라도) 유형을 '담보'로 하고, "
    "금액·한도 없이 이름만 나열된 항목이면(별도 특약·요율 목록) 유형을 '부가'로 한다. "
    "여러 이름을 묶는 섹션·그룹 표제(예: '기본계약', '보험료 할인특약', "
    "'보장확대 및 기타 특약', '특별요율')는 담보도 특약도 아니므로 행으로 만들지 마라. "
    "'부가' 항목은 이름만 정확히 옮긴다."
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
        strict_ids = {id(table) for table in strict}
        name_only = [
            table
            for table in tables
            if id(table) not in strict_ids and _is_coverage_table(table, require_amount=False)
        ]
        return strict + name_only
    return [table for table in tables if _is_coverage_table(table, require_amount=False)]


def build_coverage_source(doc: ParsedDocument) -> str:
    """LLM input for coverage extraction, via the tiered detection above."""
    tables: list[_TableRows] = []
    for table in doc.tables:
        tables.append([list(row) for row in table])

    selected = _select_coverage_tables(tables)
    if selected:
        source = "\n\n".join(md for table in selected if (md := serialize_table(table)))
    else:
        # Tier 3: no coverage table detected — hand the LLM everything we have.
        parts = [md for table in tables if (md := serialize_table(table))]
        if doc.layout_text:
            parts.append(doc.layout_text)
        source = "\n".join(parts).strip()
    return source[:_MAX_SOURCE_CHARS]


# ---------------------------------------------------------------------------
# LLM normalization: any column layout -> the unified Coverage shape


def _same_ignoring_whitespace(left: str, right: str) -> bool:
    return re.sub(r"\s", "", left) == re.sub(r"\s", "", right)


def _normalized_header_name(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", value).casefold()


def _is_section_header_name(value: str) -> bool:
    normalized = _normalized_header_name(value)
    return normalized in _SECTION_HEADER_NAMES


def _is_notice_name(value: str) -> bool:
    normalized = _normalized_header_name(value)
    return len(normalized) >= 30 and any(marker in normalized for marker in _NOTICE_NAME_MARKERS)


def _is_rate_name(value: str) -> bool:
    return "요율" in _normalized_header_name(value)


def _should_skip_coverage_name(value: str) -> bool:
    return _is_section_header_name(value) or _is_rate_name(value) or _is_notice_name(value)


def _coverage_identity(value: str) -> str:
    return _normalized_header_name(value)


def _looks_like_standalone_coverage_name(value: str) -> bool:
    """True when a wrapped-looking row is more likely a separate coverage name."""
    stripped = value.strip()
    if not stripped or _should_skip_coverage_name(stripped):
        return False
    normalized = _normalized_header_name(stripped)
    if any(marker in normalized for marker in _STRONG_COVERAGE_NAME_MARKERS):
        return True
    if any(marker in stripped for marker in _DETAIL_SENTENCE_MARKERS):
        return False

    return any(marker in normalized for marker in _COVERAGE_NAME_MARKERS)


def _markdown_tables(source: str) -> list[list[list[str]]]:
    """Each markdown table in the source as rows of cells.

    Tables are separated by blank lines; separator rows (| --- |) are dropped.
    Every table keeps its own header row so column lookups stay per-table.
    """
    tables: list[list[list[str]]] = []
    for block in source.split("\n\n"):
        rows: list[list[str]] = []
        for line in block.splitlines():
            stripped = line.strip()
            if not stripped.startswith("|"):
                continue
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if all(cell == "---" for cell in cells):
                continue
            rows.append(cells)
        if rows:
            tables.append(rows)
    return tables


def _amount_column_index(header: list[str]) -> int | None:
    """Which column holds amounts, judged by the table's own header.

    A column titled with an amount header (가입금액, 한도, …) is trusted. An
    UNTITLED column right next to the name is also trusted — auto tables print
    the limit there. A column with any OTHER title (보장상세 등) is never an
    amount column: recovering from it would stuff a description into the amount.
    """
    for index, cell in enumerate(header[1:], start=1):
        if any(amount_header in cell for amount_header in _AMOUNT_HEADERS):
            return index
    if len(header) >= 2 and not header[1]:
        return 1
    return None


def _header_column_index(header: list[str], candidates: tuple[str, ...]) -> int | None:
    for index, cell in enumerate(header):
        if any(candidate in cell for candidate in candidates):
            return index
    return None


def _name_column_index(header: list[str]) -> int | None:
    """Column containing coverage names.

    Most tables have an explicit name header (가입담보/담보명/담보종목). Some
    policies use a compact table shaped as 구분 | 보장내용 | 기간 | 가입금액, where
    the first row in 보장내용 is the coverage name and following wrapped rows are
    details. Treat 보장내용 as the name column only when no stronger name header
    exists.
    """
    explicit = _header_column_index(header, _NAME_COLUMN_HEADERS)
    if explicit is not None:
        return explicit
    return _header_column_index(header, ("보장내용",))


def _continuation_detail(
    rows: list[list[str]], start_index: int, name_column: int, amount_column: int
) -> str | None:
    """Detail text in wrapped rows following a coverage row."""
    details: list[str] = []
    for cells in rows[start_index + 1 :]:
        if len(cells) <= max(name_column, amount_column):
            continue

        has_previous_marker = any(cell.strip() for cell in cells[:name_column])
        has_amount = bool(cells[amount_column].strip())
        if has_previous_marker or has_amount:
            break

        detail = cells[name_column].strip()
        if _looks_like_standalone_coverage_name(detail):
            break
        if detail:
            details.append(detail)

    return "\n".join(details) or None


def _continuation_amount(
    rows: list[list[str]], start_index: int, name_column: int, amount_column: int
) -> str:
    """Amount text wrapped onto following rows for the same coverage."""
    amounts: list[str] = []
    for cells in rows[start_index + 1 :]:
        if len(cells) <= max(name_column, amount_column):
            continue

        has_previous_marker = any(cell.strip() for cell in cells[:name_column])
        name_text = cells[name_column].strip()
        if has_previous_marker or _looks_like_standalone_coverage_name(name_text):
            break

        amount = cells[amount_column].strip()
        if amount:
            amounts.append(amount)
            continue

        if name_text:
            break

    return "\n".join(amounts)


def _is_continuation_row(cells: list[str], name_column: int, amount_column: int) -> bool:
    if len(cells) <= max(name_column, amount_column):
        return False
    if cells[amount_column].strip():
        return False
    if _looks_like_standalone_coverage_name(cells[name_column]):
        return False
    return name_column > 0 and not any(cell.strip() for cell in cells[:name_column])


def _table_rows_to_coverages(rows: list[list[str]]) -> list[Coverage]:
    if not rows:
        return []

    header_index: int | None = None
    for index, candidate in enumerate(rows):
        if _name_column_index(candidate) is not None:
            header_index = index
            break

    if header_index is None:
        return []

    header = rows[header_index]
    name_column = _name_column_index(header)
    amount_column = _amount_column_index(header)
    if name_column is None:
        return []

    detail_column = _header_column_index(header, _DETAIL_HEADERS)
    if detail_column == name_column:
        detail_column = None

    source = "\n".join("|".join(row) for row in rows)
    coverages: list[Coverage] = []
    seen: set[str] = set()
    for index, cells in enumerate(rows[header_index + 1 :], start=header_index + 1):
        required_columns = [name_column]
        if amount_column is not None:
            required_columns.append(amount_column)
        if detail_column is not None:
            required_columns.append(detail_column)
        if len(cells) <= max(required_columns):
            continue
        if amount_column is not None and _is_continuation_row(cells, name_column, amount_column):
            continue

        name = cells[name_column].strip()
        raw_amount = cells[amount_column].strip() if amount_column is not None else ""
        if not raw_amount and amount_column is not None:
            raw_amount = _continuation_amount(rows, index, name_column, amount_column)
        if name and not _should_skip_coverage_name(name):
            row_type: Literal["담보", "부가"] = "담보" if raw_amount else "부가"
            detail = (
                cells[detail_column].strip()
                if detail_column is not None and len(cells) > detail_column
                else None
            )
            if detail is None and amount_column is not None:
                detail = _continuation_detail(rows, index, name_column, amount_column)
            parsed = _CoverageRow(
                담보명=name,
                가입금액=raw_amount,
                보장내용=detail or None,
                유형=row_type,
            )
            coverages.append(_coverage_from_row(parsed, source))
            seen.add(_coverage_identity(name))

        ignored_columns = {name_column}
        if amount_column is not None:
            ignored_columns.add(amount_column)
        if detail_column is not None:
            ignored_columns.add(detail_column)

        for column, cell in enumerate(cells):
            auxiliary_name = cell.strip()
            if column in ignored_columns or not _looks_like_standalone_coverage_name(
                auxiliary_name
            ):
                continue
            identity = _coverage_identity(auxiliary_name)
            if identity in seen:
                continue
            auxiliary = _CoverageRow(
                담보명=auxiliary_name,
                가입금액="",
                보장내용=None,
                유형="부가",
            )
            coverages.append(_coverage_from_row(auxiliary, source))
            seen.add(identity)

    return coverages


def normalize_table_coverages(source: str) -> list[Coverage]:
    """Extract straightforward markdown coverage tables without an LLM call."""

    coverages: list[Coverage] = []
    for rows in _markdown_tables(source):
        coverages.extend(_table_rows_to_coverages(rows))
    return coverages


def _amount_from_source_row(name: str, source: str) -> str | None:
    """Recover a coverage's amount cell from the markdown source.

    The table structure is authoritative: when the LLM leaves 가입금액 empty,
    the row's own amount cell (located via _amount_column_index) is the answer —
    grounded by construction since it comes straight from the source. Handles
    pdfplumber splitting a value onto a continuation row (empty name cell).
    """
    target = re.sub(r"\s", "", name)
    if not target:
        return None

    for rows in _markdown_tables(source):
        amount_column = _amount_column_index(rows[0])
        if amount_column is None:
            continue

        for index, cells in enumerate(rows):
            if len(cells) <= amount_column or re.sub(r"\s", "", cells[0]) != target:
                continue
            if cells[amount_column]:
                return cells[amount_column]
            # pdfplumber sometimes wraps the value onto a continuation row
            # (empty name cell, value in the amount cell) — look one row ahead.
            next_row = rows[index + 1] if index + 1 < len(rows) else None
            is_continuation = (
                next_row is not None and len(next_row) > amount_column and not next_row[0]
            )
            if is_continuation and next_row is not None and next_row[amount_column]:
                return next_row[amount_column]
            return None

    return None


def _detail_from_source_row(name: str, source: str) -> str | None:
    target = re.sub(r"\s", "", name)
    if not target:
        return None

    for rows in _markdown_tables(source):
        header = rows[0]
        name_column = _name_column_index(header)
        detail_column = _header_column_index(header, _DETAIL_HEADERS)
        if name_column is None or detail_column is None or detail_column == name_column:
            continue

        for index, cells in enumerate(rows):
            if len(cells) <= max(name_column, detail_column):
                continue
            if re.sub(r"\s", "", cells[name_column]) != target:
                continue
            detail = cells[detail_column].strip()
            if detail:
                return detail
            amount_column = _amount_column_index(header)
            if amount_column is not None:
                return _continuation_detail(rows, index, name_column, amount_column)

    return None


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


def _resolve_amount_and_type(
    parsed: _CoverageRow, source: str
) -> tuple[str, Literal["담보", "부가"]]:
    """The row's verbatim amount and its 담보/부가 type, table structure first.

    The source table is more reliable than the LLM's field mapping: when the
    LLM left 가입금액 empty but the row's own amount cell has content, that
    cell is the amount — and a row with an amount cell is a coverage, whatever
    the LLM called it (긴급출동특약-style rows).
    """
    raw_amount = parsed.가입금액.strip()
    if raw_amount:
        return raw_amount, parsed.유형

    recovered = _amount_from_source_row(parsed.담보명, source)
    if recovered:
        return recovered, "담보"

    return "", parsed.유형


def _resolve_detail(parsed: _CoverageRow, raw_amount: str, source: str) -> str | None:
    """The row's policy wording, or None when a 해설 should be generated instead.

    Dropped when it is not verbatim policy text (anti-hallucination), or when it
    merely repeats the amount cell — a limit phrase copied into both fields
    describes the amount, not the coverage.
    """
    detail = parsed.보장내용.strip() if parsed.보장내용 else None
    if not detail:
        detail = _detail_from_source_row(parsed.담보명, source)
        if not detail:
            return None
    if not wording_grounded(detail, source):
        return None
    if _same_ignoring_whitespace(detail, raw_amount):
        return None
    return detail


def _display_amount(raw_amount: str, row_type: str, source: str) -> str:
    """The amount as shown to the user.

    담보 rows always answer the amount question — an empty cell becomes 확인필요
    ("check the policy terms"). 부가 rows are name-only riders/rates, so an
    empty amount is their expected shape, not a verification gap.
    """
    if row_type != "담보" and not raw_amount:
        return ""
    return normalize_amount(raw_amount, source)


def _coverage_from_row(parsed: _CoverageRow, source: str) -> Coverage:
    """One LLM row -> one Coverage, applying the field-completeness policy:

    - name + amount + wording: everything shown verbatim
    - amount but no wording:   wording None -> a 해설 is generated downstream
    - wording but no amount:   amount 확인필요 -> UI points at the policy terms
    - name only (부가 row):    name-only display, no 해설, empty amount
    """
    raw_amount, row_type = _resolve_amount_and_type(parsed, source)
    detail = _resolve_detail(parsed, raw_amount, source)
    if not raw_amount and not detail:
        row_type = "부가"

    coverage = Coverage(
        담보명=parsed.담보명.strip(),
        가입금액=_display_amount(raw_amount, row_type, source),
        보장내용=detail,
        해설=None,
    )
    if row_type != "담보":
        coverage["유형"] = row_type  # omit for 담보 rows — preserve response shape
    return coverage


def normalize_coverages(source: str, complete: JsonCompleter | None = None) -> list[Coverage]:
    """Map a coverage-table source into Coverages (one structured LLM call)."""
    if not source.strip():
        return []

    if complete is None:
        local_coverages = normalize_table_coverages(source)
        if local_coverages:
            return local_coverages

    completer = complete or _default_completer()
    model_source = mask_demographic_identifiers(source)
    rows = completer(_SYSTEM, model_source).get("보장목록", [])
    if not isinstance(rows, list):
        return []

    coverages: list[Coverage] = []
    for row in rows:
        try:
            parsed = _CoverageRow.model_validate(row)
        except ValidationError:
            continue
        if _should_skip_coverage_name(parsed.담보명):
            continue
        coverages.append(_coverage_from_row(parsed, source))
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
    normalize: Normalizer = normalize_coverages,
    explain: Explainer = explain_coverages_fast,
) -> tuple[list[Coverage], str]:
    """Extract the coverage list from a parsed policy document, best-effort."""
    try:
        source = build_coverage_source(doc)
        coverages = normalize(source)
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
