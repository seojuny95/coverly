"""HTTP boundary for single-policy parsing and uploaded-text sessions."""

import asyncio

from fastapi import APIRouter, UploadFile
from pydantic import BaseModel

from app.errors import ApiError
from app.services.policy.pipeline import EmptyTextError, run_pipeline
from app.services.rag.policy import delete_policy_session, refresh_policy_session
from app.services.rag.policy.session_tokens import InvalidPolicySessionToken

router = APIRouter(prefix="/policies", tags=["policies"])

MAX_PDF_BYTES = 10 * 1024 * 1024
_CHUNK_SIZE = 1024 * 1024


class PolicySessionRequest(BaseModel):
    문서세션ID: str


class PolicySessionRefreshResponse(BaseModel):
    문서세션ID: str
    expiresAt: str


async def _read_pdf(file: UploadFile) -> bytes:
    data = b""
    while chunk := await file.read(_CHUNK_SIZE):
        data += chunk
        if len(data) > MAX_PDF_BYTES:
            raise ApiError(
                status_code=413,
                code="PDF_TOO_LARGE",
                message="파일이 너무 큽니다 (최대 10MB).",
            )
    if not data.startswith(b"%PDF-"):
        raise ApiError(
            status_code=400,
            code="INVALID_PDF",
            message="유효한 PDF 파일이 아닙니다.",
        )
    return data


@router.post("/parse")
async def parse_policy(file: UploadFile) -> dict[str, object]:
    data = await _read_pdf(file)
    try:
        result = await asyncio.to_thread(run_pipeline, data)
    except EmptyTextError:
        raise ApiError(
            status_code=422,
            code="PDF_TEXT_EXTRACTION_FAILED",
            message="PDF에서 텍스트를 추출할 수 없습니다.",
        ) from None
    return {"status": "accepted", **result}


@router.post("/sessions/delete")
def delete_policy_text_session(request: PolicySessionRequest) -> dict[str, str]:
    try:
        delete_policy_session(request.문서세션ID)
    except InvalidPolicySessionToken:
        raise ApiError(
            status_code=403,
            code="INVALID_POLICY_SESSION",
            message="분석 세션이 만료됐어요. 다시 분석하려면 보험증권을 다시 올려주세요.",
        ) from None
    return {"status": "deleted"}


@router.post("/sessions/refresh", response_model=PolicySessionRefreshResponse)
def refresh_policy_text_session(
    request: PolicySessionRequest,
) -> PolicySessionRefreshResponse:
    try:
        refreshed = refresh_policy_session(request.문서세션ID)
    except InvalidPolicySessionToken:
        raise ApiError(
            status_code=403,
            code="INVALID_POLICY_SESSION",
            message="분석 세션이 만료됐어요. 다시 분석하려면 보험증권을 다시 올려주세요.",
        ) from None
    return PolicySessionRefreshResponse(
        문서세션ID=refreshed.token,
        expiresAt=refreshed.expires_at.isoformat(),
    )
