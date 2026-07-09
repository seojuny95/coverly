"""Coverage (담보) table detection and serialization.

Real policies render the coverage list as ruled tables, so pdfplumber's default
lines strategy recovers them. Detection is tiered because the failure costs are
asymmetric — a missed table loses the whole coverage list, while a spurious one
only adds a few prompt tokens the LLM is told to ignore:

1. strict: a table whose cells contain both a name header and an amount header
2. relaxed: name header only (unusual amount column labels)
3. fallback: no match at all -> every table as markdown + layout text, so the
   worst case equals the no-detection baseline

Only extract_coverage_source is public; the tiering/serialization helpers are
internal (their behavior is covered end-to-end via extract_coverage_source on
real sample policies).
"""

import io

import pdfplumber

_TableRows = list[list[str | None]]

# Header vocabulary observed across sample policies, kept intentionally wider
# than the samples so unseen insurers still match tier 1.
_NAME_HEADERS = ("보장명", "담보명", "담보종목", "보장상세", "특약명")
_AMOUNT_HEADERS = ("가입금액", "보험가입금액", "보장금액", "보험금액", "한도")


def _flatten(rows: _TableRows) -> str:
    return " ".join(cell or "" for row in rows for cell in row)


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


def _serialize_table(rows: _TableRows) -> str:
    """Render a pdfplumber table as markdown so column-row associations survive.

    Cell-internal newlines become ' / ' (cells often pack several line items).
    Returns '' for non-tables (<2 rows or <2 columns).
    """
    clean = [[(cell or "").replace("\n", " / ").strip() for cell in row] for row in rows]
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


def extract_coverage_source(pdf_bytes: bytes) -> str:
    """LLM input for coverage extraction, via the tiered detection above."""
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        tables = [table for page in pdf.pages for table in page.extract_tables()]
        selected = _select_coverage_tables(tables)
        if selected:
            parts = [md for table in selected if (md := _serialize_table(table))]
            return "\n\n".join(parts)
        # Tier 3: no coverage table detected — hand the LLM everything we have.
        parts = [md for table in tables if (md := _serialize_table(table))]
        parts.extend(page.extract_text(layout=True) or "" for page in pdf.pages)
        return "\n".join(parts).strip()
