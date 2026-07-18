"""Deterministic source selection and table parsing for policy coverages."""

import re

from app.core.grounding import normalize_amount, wording_grounded
from app.core.tables import serialize_table
from app.modules.policy.models import Coverage, CoverageType, ParsedDocument

_TableRows = list[list[str | None]]

# Upper bound on the source handed to the LLM. The tier-3 fallback can dump every
# page's layout text, so cap it to bound model input and cost on large PDFs.
DEFAULT_MAX_SOURCE_CHARS = 30_000

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


def build_coverage_source(
    doc: ParsedDocument,
    *,
    max_chars: int = DEFAULT_MAX_SOURCE_CHARS,
) -> str:
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
    return source[:max_chars]


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


def should_skip_coverage_name(value: str) -> bool:
    return _is_section_header_name(value) or _is_rate_name(value) or _is_notice_name(value)


def _coverage_identity(value: str) -> str:
    return _normalized_header_name(value)


def _has_previous_column_value(cells: list[str], name_column: int) -> bool:
    return any(cell.strip() for cell in cells[:name_column])


def _looks_like_standalone_coverage_name(value: str) -> bool:
    """True when a wrapped-looking row is more likely a separate coverage name."""
    stripped = value.strip()
    if not stripped or should_skip_coverage_name(stripped):
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

        has_previous_marker = _has_previous_column_value(cells, name_column)
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

        name_text = cells[name_column].strip()
        if _has_previous_column_value(cells, name_column) or _looks_like_standalone_coverage_name(
            name_text
        ):
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
    return name_column > 0 and not _has_previous_column_value(cells, name_column)


def _required_columns(
    name_column: int,
    amount_column: int | None,
    detail_column: int | None,
) -> list[int]:
    columns = [name_column]
    if amount_column is not None:
        columns.append(amount_column)
    if detail_column is not None:
        columns.append(detail_column)
    return columns


def _ignored_auxiliary_columns(
    name_column: int,
    amount_column: int | None,
    detail_column: int | None,
) -> set[int]:
    columns = {name_column}
    if amount_column is not None:
        columns.add(amount_column)
    if detail_column is not None:
        columns.add(detail_column)
    return columns


def _append_auxiliary_coverages(
    coverages: list[Coverage],
    seen: set[str],
    cells: list[str],
    ignored_columns: set[int],
    source: str,
) -> None:
    for column, cell in enumerate(cells):
        auxiliary_name = cell.strip()
        if column in ignored_columns or not _looks_like_standalone_coverage_name(auxiliary_name):
            continue

        identity = _coverage_identity(auxiliary_name)
        if identity in seen:
            continue

        auxiliary = coverage_from_values(
            name=auxiliary_name,
            amount="",
            detail=None,
            row_type="부가",
            source=source,
        )
        coverages.append(auxiliary)
        seen.add(identity)


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
        if len(cells) <= max(_required_columns(name_column, amount_column, detail_column)):
            continue
        if amount_column is not None and _is_continuation_row(cells, name_column, amount_column):
            continue

        name = cells[name_column].strip()
        raw_amount = cells[amount_column].strip() if amount_column is not None else ""
        if not raw_amount and amount_column is not None:
            raw_amount = _continuation_amount(rows, index, name_column, amount_column)
        if name and not should_skip_coverage_name(name):
            row_type: CoverageType = "담보" if raw_amount else "부가"
            detail = (
                cells[detail_column].strip()
                if detail_column is not None and len(cells) > detail_column
                else None
            )
            if detail is None and amount_column is not None:
                detail = _continuation_detail(rows, index, name_column, amount_column)
            coverage = coverage_from_values(
                name=name,
                amount=raw_amount,
                detail=detail or None,
                row_type=row_type,
                source=source,
            )
            coverages.append(coverage)
            seen.add(_coverage_identity(name))

        _append_auxiliary_coverages(
            coverages,
            seen,
            cells,
            _ignored_auxiliary_columns(name_column, amount_column, detail_column),
            source,
        )

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
        header = rows[0]
        name_column = _name_column_index(header)
        amount_column = _amount_column_index(header)
        if name_column is None or amount_column is None:
            continue

        for index, cells in enumerate(rows):
            if len(cells) <= max(name_column, amount_column):
                continue
            if re.sub(r"\s", "", cells[name_column]) != target:
                continue
            if cells[amount_column]:
                return cells[amount_column]
            return _continuation_amount(rows, index, name_column, amount_column) or None

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


def _resolve_amount_and_type(
    name: str,
    amount: str,
    row_type: CoverageType,
    source: str,
) -> tuple[str, CoverageType]:
    """The row's verbatim amount and its 담보/부가 type, table structure first.

    The source table is more reliable than the LLM's field mapping: when the
    LLM left 가입금액 empty but the row's own amount cell has content, that
    cell is the amount — and a row with an amount cell is a coverage, whatever
    the LLM called it (긴급출동특약-style rows).
    """
    raw_amount = amount.strip()
    if raw_amount:
        return raw_amount, row_type

    recovered = _amount_from_source_row(name, source)
    if recovered:
        return recovered, "담보"

    return "", row_type


def _resolve_detail(
    name: str,
    detail: str | None,
    raw_amount: str,
    source: str,
) -> str | None:
    """The row's policy wording, or None when a 해설 should be generated instead.

    Dropped when it is not verbatim policy text (anti-hallucination), or when it
    merely repeats the amount cell — a limit phrase copied into both fields
    describes the amount, not the coverage.
    """
    resolved = detail.strip() if detail else None
    if not resolved:
        resolved = _detail_from_source_row(name, source)
        if not resolved:
            return None
    if not wording_grounded(resolved, source):
        return None
    if _same_ignoring_whitespace(resolved, raw_amount):
        return None
    return resolved


def _display_amount(raw_amount: str, row_type: str, source: str) -> str:
    """The amount as shown to the user.

    담보 rows always answer the amount question — an empty cell becomes 확인필요
    ("check the policy terms"). 부가 rows are name-only riders/rates, so an
    empty amount is their expected shape, not a verification gap.
    """
    if row_type != "담보" and not raw_amount:
        return ""
    return normalize_amount(raw_amount, source)


def coverage_from_values(
    *,
    name: str,
    detail: str | None,
    amount: str,
    row_type: CoverageType,
    source: str,
) -> Coverage:
    """Build one grounded coverage from parsed row values.

    - name + amount + wording: everything shown verbatim
    - amount but no wording:   wording None -> a 해설 is generated downstream
    - wording but no amount:   amount 확인필요 -> UI points at the policy terms
    - name only (부가 row):    name-only display, no 해설, empty amount
    """
    raw_amount, resolved_type = _resolve_amount_and_type(name, amount, row_type, source)
    resolved_detail = _resolve_detail(name, detail, raw_amount, source)
    if not raw_amount and not resolved_detail:
        resolved_type = "부가"

    coverage = Coverage(
        담보명=name.strip(),
        가입금액=_display_amount(raw_amount, resolved_type, source),
        보장내용=resolved_detail,
        해설=None,
    )
    if resolved_type != "담보":
        coverage["유형"] = resolved_type
    return coverage
