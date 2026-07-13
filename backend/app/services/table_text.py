"""Shared rendering helpers for tables extracted from policy PDFs."""

from collections.abc import Sequence


def serialize_table(rows: Sequence[Sequence[str | None]]) -> str:
    """Render a table as markdown while preserving row-column associations."""
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


def _join_cell_lines(cell: str) -> str:
    return " ".join(cell.split())
