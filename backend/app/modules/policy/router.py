"""HTTP boundary for single-policy parsing and uploaded-text sessions."""

import asyncio
from typing import Annotated, Protocol
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.core.errors import ApiError, api_error_responses
from app.modules.policy.parsing import (
    PdfPasswordIncorrectError,
    PdfPasswordRequiredError,
)
from app.modules.policy.pipeline import EmptyTextError, PipelineResult, run_pipeline
from app.modules.policy.schemas import PolicyParseResponse
from app.modules.portfolio.session.dependencies import PortfolioSessionServiceDep
from app.modules.portfolio.session.service import (
    InvalidPortfolioSessionToken,
    PortfolioSessionDocumentCancelled,
    PortfolioSessionDocumentLimitExceeded,
)
from app.modules.reference_data.loader import ReferenceDataUnavailableError

router = APIRouter(prefix="/policies", tags=["policies"])

MAX_PDF_BYTES = 10 * 1024 * 1024
_CHUNK_SIZE = 1024 * 1024
_PDF_UPLOAD_DESCRIPTION = (
    "PDF document only. The server verifies the %PDF signature and accepts at most "
    f"{MAX_PDF_BYTES // (1024 * 1024)} MiB."
)


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


@router.post(
    "/parse",
    response_model=PolicyParseResponse,
    response_model_exclude_unset=True,
    responses=api_error_responses(400, 403, 409, 413, 422, 503),
)
async def parse_policy(
    file: Annotated[
        UploadFile,
        File(
            media_type="application/pdf",
            description=_PDF_UPLOAD_DESCRIPTION,
            json_schema_extra={
                "contentMediaType": "application/pdf",
                "format": "binary",
                "x-maxBytes": MAX_PDF_BYTES,
            },
        ),
    ],
    pipeline: PolicyPipelineDep,
    sessions: PortfolioSessionServiceDep,
    document_id: Annotated[UUID, Form(alias="documentId")],
    password: str | None = Form(default=None),
    portfolio_session_token: str = Form(
        alias="portfolioSessionToken",
        min_length=1,
        max_length=512,
    ),
) -> PolicyParseResponse:
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
    except ReferenceDataUnavailableError as exc:
        raise ApiError(
            status_code=503,
            code="reference_data_unavailable",
            message="분석 기준 정보를 불러오지 못했어요. 잠시 후 다시 시도해주세요.",
        ) from exc
    try:
        document = await asyncio.to_thread(
            sessions.add_pipeline_result,
            portfolio_session_token,
            result,
            document_id=document_id.hex,
        )
    except InvalidPortfolioSessionToken:
        raise ApiError(
            status_code=403,
            code="INVALID_PORTFOLIO_SESSION",
            message="분석 세션이 만료됐어요. 보험증권을 다시 올려주세요.",
        ) from None
    except PortfolioSessionDocumentLimitExceeded:
        raise ApiError(
            status_code=422,
            code="PORTFOLIO_DOCUMENT_LIMIT_EXCEEDED",
            message="한 번에 분석할 수 있는 보험증권 수를 초과했어요.",
        ) from None
    except PortfolioSessionDocumentCancelled:
        raise ApiError(
            status_code=409,
            code="POLICY_UPLOAD_CANCELLED",
            message="취소된 업로드예요. 파일을 다시 선택해주세요.",
        ) from None

    client_result = dict(result)
    client_result.pop("문서세션ID", None)
    return PolicyParseResponse.model_validate(
        {
            "status": "accepted",
            "document_id": document.id,
            **client_result,
        }
    )
