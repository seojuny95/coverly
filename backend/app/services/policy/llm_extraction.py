import json
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI
from openai.types.responses import EasyInputMessageParam, ResponseTextConfigParam

from app.services.policy.summary_types import CoveragePeriod, PolicyCoreSummary, PremiumSummary
from app.settings import get_settings

LlmPolicySummary = PolicyCoreSummary


JsonObject = dict[str, Any]

_MAX_INPUT_CHARS = 30_000
_INSURER_CATALOG_PATH = Path(__file__).with_name("insurer_catalog.json")
_STRING_OR_NULL_SCHEMA: JsonObject = {"type": ["string", "null"]}
_INTEGER_OR_NULL_SCHEMA: JsonObject = {"type": ["integer", "null"]}
_SUMMARY_STRING_FIELDS = (
    "보험사",
    "상품명",
    "증권번호",
    "계약자",
    "피보험자",
    "만기일",
    "납입기간",
)
_SUMMARY_REQUIRED_FIELDS = [
    "보험사",
    "상품명",
    "증권번호",
    "계약자",
    "피보험자",
    "보험기간",
    "만기일",
    "납입기간",
    "보험료",
]
_SYSTEM_PROMPT = (
    "너는 한국 보험증권 PDF에서 표시용 핵심 필드만 추출한다. "
    "보험사는 보험계약을 인수하거나 증권을 발행한 보험회사명이다. "
    "상품명, 브랜드명, 플랜명, 부서명, 모집/품질보증 담당자명은 보험사가 아니다. "
    "보험사는 반드시 사용자가 제공한 후보 목록 중 하나만 선택한다. "
    "후보 중 어느 보험사인지 확인할 수 없으면 null로 둔다."
)


@lru_cache
def get_insurer_candidates() -> tuple[str, ...]:
    payload = json.loads(_INSURER_CATALOG_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("insurer catalog must be a JSON list")

    candidates = tuple(value for value in payload if isinstance(value, str) and value.strip())
    if not candidates:
        raise ValueError("insurer catalog must contain at least one insurer")

    return candidates


@lru_cache
def _get_openai_client(api_key: str) -> OpenAI:
    return OpenAI(api_key=api_key)


def extract_policy_summary_with_llm(text: str) -> LlmPolicySummary | None:
    settings = get_settings()
    if not settings.openai_api_key:
        return None

    insurer_candidates = get_insurer_candidates()
    response_text = _request_summary_text(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        response_format=_build_response_format(insurer_candidates),
        messages=_build_messages(text, insurer_candidates),
    )
    if response_text is None:
        return None

    raw_summary = _parse_json_object(response_text)
    if raw_summary is None:
        return None

    return _coerce_policy_summary(raw_summary, insurer_candidates)


def _build_messages(text: str, insurer_candidates: tuple[str, ...]) -> list[EasyInputMessageParam]:
    insurer_list = "\n".join(f"- {insurer}" for insurer in insurer_candidates)
    truncated_text = text[:_MAX_INPUT_CHARS]

    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "다음 텍스트에서 보험사, 상품명, 증권번호, 계약자, 피보험자, "
                "보험기간, 만기일, 납입기간, 보험료를 추출해.\n"
                "보험사 후보 목록:\n"
                f"{insurer_list}\n\n"
                "보험사에는 후보 목록에 없는 상품명이나 브랜드명을 넣지 마. "
                "후보 목록의 실제 보험회사와 명확히 연결되는 경우에만 후보명을 선택해.\n\n"
                f"{truncated_text}"
            ),
        },
    ]


def _build_response_format(insurer_candidates: tuple[str, ...]) -> JsonObject:
    return {
        "format": {
            "type": "json_schema",
            "name": "policy_summary_extraction",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "보험사": {
                        "type": ["string", "null"],
                        "enum": [*insurer_candidates, None],
                    },
                    "상품명": _STRING_OR_NULL_SCHEMA,
                    "증권번호": _STRING_OR_NULL_SCHEMA,
                    "계약자": _STRING_OR_NULL_SCHEMA,
                    "피보험자": _STRING_OR_NULL_SCHEMA,
                    "보험기간": _build_coverage_period_schema(),
                    "만기일": _STRING_OR_NULL_SCHEMA,
                    "납입기간": _STRING_OR_NULL_SCHEMA,
                    "보험료": _build_premium_schema(),
                },
                "required": _SUMMARY_REQUIRED_FIELDS,
            },
        }
    }


def _build_coverage_period_schema() -> JsonObject:
    return {
        "type": ["object", "null"],
        "additionalProperties": False,
        "properties": {
            "시작일": _STRING_OR_NULL_SCHEMA,
            "종료일": _STRING_OR_NULL_SCHEMA,
        },
        "required": ["시작일", "종료일"],
    }


def _build_premium_schema() -> JsonObject:
    return {
        "type": ["object", "null"],
        "additionalProperties": False,
        "properties": {
            "금액": _INTEGER_OR_NULL_SCHEMA,
            "납입주기": _STRING_OR_NULL_SCHEMA,
        },
        "required": ["금액", "납입주기"],
    }


def _request_summary_text(
    *,
    api_key: str,
    model: str,
    response_format: JsonObject,
    messages: list[EasyInputMessageParam],
) -> str | None:
    client = _get_openai_client(api_key)

    try:
        response = client.responses.create(
            model=model,
            input=cast(Any, messages),
            text=cast(ResponseTextConfigParam, response_format),
            temperature=0,
        )
    except (APIConnectionError, APIStatusError, APITimeoutError):
        return None

    response_text = response.output_text
    if not isinstance(response_text, str):
        return None

    normalized = response_text.strip()
    return normalized or None


def _parse_json_object(value: str) -> JsonObject | None:
    try:
        parsed = json.loads(_strip_json_code_fence(value))
    except json.JSONDecodeError:
        return None

    return parsed if isinstance(parsed, dict) else None


def _strip_json_code_fence(value: str) -> str:
    stripped = value.strip()
    if not stripped.startswith("```"):
        return stripped

    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]

    return "\n".join(lines).strip()


def _coerce_policy_summary(
    raw_summary: JsonObject,
    insurer_candidates: tuple[str, ...],
) -> LlmPolicySummary:
    summary: LlmPolicySummary = {}

    for key in _SUMMARY_STRING_FIELDS:
        value = _coerce_non_empty_string(raw_summary.get(key))
        if value is None:
            continue
        if key == "보험사" and value not in insurer_candidates:
            continue
        summary[key] = value  # type: ignore[literal-required]

    coverage_period = _coerce_coverage_period(raw_summary.get("보험기간"))
    if coverage_period:
        summary["보험기간"] = coverage_period

    premium = _coerce_premium_summary(raw_summary.get("보험료"))
    if premium:
        summary["보험료"] = premium

    return summary


def _coerce_coverage_period(value: object) -> CoveragePeriod | None:
    if not isinstance(value, dict):
        return None

    coverage_period: CoveragePeriod = {}
    start_date = _coerce_non_empty_string(value.get("시작일"))
    if start_date is not None:
        coverage_period["시작일"] = start_date

    end_date = _coerce_non_empty_string(value.get("종료일"))
    if end_date is not None:
        coverage_period["종료일"] = end_date

    return coverage_period or None


def _coerce_premium_summary(value: object) -> PremiumSummary | None:
    if not isinstance(value, dict):
        return None

    premium: PremiumSummary = {}
    amount = value.get("금액")
    if isinstance(amount, int):
        premium["금액"] = amount

    payment_cycle = _coerce_non_empty_string(value.get("납입주기"))
    if payment_cycle is not None:
        premium["납입주기"] = payment_cycle

    return premium or None


def _coerce_non_empty_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None

    normalized = value.strip()
    return normalized or None
