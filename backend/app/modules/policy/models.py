"""Domain types shared across the policy-processing pipeline."""

from dataclasses import dataclass
from typing import Literal, NotRequired, TypedDict

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

    보장내용 is the policy's own wording (authoritative); 해설 is a generated
    general explanation, filled only when 보장내용 is absent.
    """

    담보명: str
    가입금액: str
    보장내용: str | None
    해설: str | None
    유형: NotRequired[Literal["담보", "부가"]]
    # 유형 absent defaults to "담보"; "부가" marks name-only riders or rate rows.


class VehicleInfo(TypedDict, total=False):
    """Vehicle details extracted from policy summary."""

    차량명: str
    차량번호: str
    연식: str


class CoveragePeriod(TypedDict, total=False):
    시작일: str
    종료일: str


class PremiumSummary(TypedDict, total=False):
    금액: int
    납입주기: str


InsuredGender = Literal["남성", "여성"]
LifeStage = Literal["어린이", "성인", "시니어"]
PolicyAnalysisStatus = Literal["완료", "부분"]


class InsuredDemographics(TypedDict):
    """Non-identifying insured attributes derived locally from the policy."""

    나이: int
    성별: InsuredGender
    생애단계: LifeStage


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
    피보험자정보: InsuredDemographics
    차량정보: VehicleInfo


class PolicySummary(PolicyCoreSummary, total=False):
    보험분류: str
    상품태그: list[str]


class PolicyClassification(TypedDict):
    보험분류: str
    상품태그: list[str]
