"""Normalize a coverage-table source into the unified Coverage shape.

Insurers print the coverage table with different columns; one structured-output
LLM call maps any layout into the same fields. The LLM only transcribes rows
that exist in the source — amounts it returns are then grounded against the
source and demoted to 확인필요 when unverifiable (see amount.normalize_amount).
"""

from functools import lru_cache

from pydantic import BaseModel, ValidationError

from app.services.coverage.amount import normalize_amount
from app.services.coverage.types import Coverage
from app.services.llm import JsonCompleter, structured_completer

_SYSTEM = (
    "너는 보험 증권의 담보(보장) 표를 통일된 형식으로 정리하는 도우미다. "
    "입력은 증권에서 추출한 담보표 마크다운(또는 레이아웃 텍스트)이다. "
    "열 제목(보장명·담보명·담보종목·보장상세·보장내용·가입금액 등)을 보고 각 값을 정확히 매핑하라. "
    "표에 실제로 있는 담보만 옮기고 새로 지어내지 마라. "
    "담보명은 증권 표기를 살리되, 보장 대상·사고를 바꾸지 않는 순수 부가어는 "
    "괄호 안이라도 제거한다 "
    "— '감액없음'·'감액'·'기본계약'·'주계약'·'선택'·'무배당' 같은 지급방식·계약형태 표시. "
    "예: '암진단비(유사암제외)(감액없음)'→'암진단비(유사암제외)'. "
    "'기본계약(일반상해후유장해(80%이상))'처럼 담보명을 감싸는 접두 래퍼는 바깥 래퍼만 벗긴다. "
    "반대로 '유사암제외'·'80%이상'·'1~5종'처럼 보장 범위·지급조건을 가르는 수식어는 반드시 남긴다. "
    "보장내용은 증권 원문 그대로 옮긴다(요약·축약 금지, '※'로 시작하는 단서 포함). 없으면 null. "
    "가입금액이 없으면 빈 문자열로 둔다."
)


class _CoverageRow(BaseModel):
    담보명: str
    보장내용: str | None
    가입금액: str


class _CoverageList(BaseModel):
    보장목록: list[_CoverageRow]


@lru_cache
def _default_completer() -> JsonCompleter:
    return structured_completer(_CoverageList)


def normalize_coverages(source: str, complete: JsonCompleter | None = None) -> list[Coverage]:
    """Map a coverage-table source into Coverages (one structured LLM call)."""
    if not source.strip():
        return []
    completer = complete or _default_completer()
    rows = completer(_SYSTEM, source).get("보장목록", [])
    if not isinstance(rows, list):
        return []

    coverages: list[Coverage] = []
    for row in rows:
        try:
            parsed = _CoverageRow.model_validate(row)
        except ValidationError:
            continue
        detail = parsed.보장내용.strip() if parsed.보장내용 else None
        coverages.append(
            Coverage(
                담보명=parsed.담보명.strip(),
                가입금액=normalize_amount(parsed.가입금액, source),
                보장내용=detail or None,
                해설=None,
            )
        )
    return coverages
