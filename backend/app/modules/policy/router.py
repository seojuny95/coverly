"""HTTP boundary for single-policy parsing and uploaded-text sessions."""

import asyncio
from typing import Annotated, Protocol

from fastapi import APIRouter, Depends, Form, UploadFile

from app.core.errors import ApiError
from app.modules.policy.parsing import (
    PdfPasswordIncorrectError,
    PdfPasswordRequiredError,
)
from app.modules.policy.pipeline import EmptyTextError, PipelineResult, run_pipeline
from app.modules.policy.schemas import (
    PolicySessionRefreshResponse,
    PolicySessionRequest,
)
from app.rag.policy import delete_policy_session, refresh_policy_session
from app.rag.policy.session_tokens import InvalidPolicySessionToken

router = APIRouter(prefix="/policies", tags=["policies"])

MAX_PDF_BYTES = 10 * 1024 * 1024
_CHUNK_SIZE = 1024 * 1024


class PolicyPipeline(Protocol):
    def __call__(self, pdf_bytes: bytes, *, password: str | None = None) -> PipelineResult: ...


def get_policy_pipeline() -> PolicyPipeline:
    return run_pipeline


PolicyPipelineDep = Annotated[PolicyPipeline, Depends(get_policy_pipeline)]


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
async def parse_policy(
    file: UploadFile,
    pipeline: PolicyPipelineDep,
    password: str | None = Form(default=None),
) -> dict[str, object]:
    data = await _read_pdf(file)
    pdf_password = password if password else None
    try:
        result = await asyncio.to_thread(pipeline, data, password=pdf_password)
    except PdfPasswordRequiredError:
        raise ApiError(
            status_code=422,
            code="PDF_PASSWORD_REQUIRED",
            message="PDF 비밀번호를 입력해주세요.",
        ) from None
    except PdfPasswordIncorrectError:
        raise ApiError(
            status_code=422,
            code="PDF_PASSWORD_INCORRECT",
            message="PDF 비밀번호가 맞지 않아요. 다시 입력해주세요.",
        ) from None
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
