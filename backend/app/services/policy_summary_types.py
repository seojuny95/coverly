from typing import TypedDict


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
