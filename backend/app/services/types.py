"""Domain types shared across the policy-processing pipeline."""

from dataclasses import dataclass
from typing import TypedDict

# A pdfplumber table: rows of cells (None = empty cell), immutable for ParsedDocument.
Table = tuple[tuple[str | None, ...], ...]


@dataclass(frozen=True)
class ParsedDocument:
    """Single-pass parse output consumed by every downstream stage.

    text: plain reading-order text (classification, summary).
    layout_text: layout-preserved text (coverage table fallback).
    tables: every table pdfplumber recovered, raw.
    """

    text: str
    layout_text: str
    tables: tuple[Table, ...]
    # NOTE: add an `images` field here if/when VLM (vector/image) parsing is needed;
    # the current pipeline targets text-layer PDFs only.


class Coverage(TypedDict):
    """One coverage (담보) row for the /policies/parse response.

    보장내용 is the policy's own wording (authoritative); 해설 is an LLM-generated
    general explanation, filled only when 보장내용 is absent.
    """

    담보명: str
    가입금액: str
    보장내용: str | None
    해설: str | None


class CoveragePeriod(TypedDict, total=False):
    시작일: str
    종료일: str


class PremiumSummary(TypedDict, total=False):
    금액: int
    납입주기: str


class PolicyCoreSummary(TypedDict, total=False):
    보험사: str
    상품명: str
    증권번호: str
    계약자: str
    피보험자: str
    보험기간: CoveragePeriod
    만기일: str
    납입기간: str
    보험료: PremiumSummary


class PolicySummary(PolicyCoreSummary, total=False):
    보험분류: str
    상품태그: list[str]


class PolicyClassification(TypedDict):
    보험분류: str
    상품태그: list[str]
