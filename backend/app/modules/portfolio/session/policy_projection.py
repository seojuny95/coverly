"""PII-minimized policy projection stored for analysis and QA."""

from collections.abc import Mapping
from datetime import datetime

from app.modules.policy.pipeline import PipelineResult
from app.modules.portfolio.schemas import PolicyInput
from app.rag.policy.pii import mask_policy_pii
from app.rag.policy.session_tokens import (
    InvalidPolicySessionToken,
    verify_policy_session_claims,
)


def rag_session_id_from_result(
    result: PipelineResult,
    *,
    now: datetime,
) -> str | None:
    token = result.get("문서세션ID")
    if token is None:
        return None
    try:
        return verify_policy_session_claims(token, now=now).session_id
    except InvalidPolicySessionToken:
        return None


def policy_for_storage(result: PipelineResult, *, document_id: str) -> PolicyInput:
    info = result["기본정보"]
    safe_info = {
        key: info[key]
        for key in (
            "보험사",
            "상품명",
            "보험분류",
            "상품태그",
            "보험기간",
            "만기일",
            "납입기간",
            "보험료",
            "피보험자정보",
        )
        if key in info
    }
    return PolicyInput.model_validate(
        {
            "id": document_id,
            "기본정보": safe_info,
            "보장목록": [_masked_coverage(item) for item in result["보장목록"]],
            "분석상태": result.get("분석상태"),
        }
    )


def _masked_coverage(coverage: Mapping[str, object]) -> dict[str, object]:
    return {
        key: mask_policy_pii(value) if isinstance(value, str) else value
        for key, value in coverage.items()
    }
