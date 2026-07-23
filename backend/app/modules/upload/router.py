"""HTTP boundary that composes policy parsing with portfolio sessions."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.core.errors import ApiError, api_error_responses
from app.modules.policy.parsing import MAX_PDF_PAGES
from app.modules.policy.pipeline import run_pipeline
from app.modules.policy.schemas import PolicyParseResponse
from app.modules.portfolio.session.dependencies import PortfolioSessionServiceDep
from app.modules.upload.parsing_capacity import (
    PdfParsingBusyError,
    PdfParsingCapacity,
    get_pdf_parsing_capacity,
)
from app.modules.upload.service import PolicyPipeline, PolicyUploadService

router = APIRouter(prefix="/policies", tags=["policies"])

MAX_PDF_BYTES = 10 * 1024 * 1024
_CHUNK_SIZE = 1024 * 1024
_PDF_UPLOAD_DESCRIPTION = (
    "PDF document only. The server verifies the %PDF signature and accepts at most "
    f"{MAX_PDF_BYTES // (1024 * 1024)} MiB and {MAX_PDF_PAGES} pages."
)


def get_policy_pipeline() -> PolicyPipeline:
    return run_pipeline


PolicyPipelineDep = Annotated[PolicyPipeline, Depends(get_policy_pipeline)]
PdfParsingCapacityDep = Annotated[PdfParsingCapacity, Depends(get_pdf_parsing_capacity)]


async def _read_pdf(file: UploadFile) -> bytes:
    chunks: list[bytes] = []
    total_bytes = 0
    while chunk := await file.read(_CHUNK_SIZE):
        total_bytes += len(chunk)
        if total_bytes > MAX_PDF_BYTES:
            raise ApiError(
                status_code=413,
                code="PDF_TOO_LARGE",
                message="파일이 너무 큽니다 (최대 10MB).",
            )
        chunks.append(chunk)
    data = b"".join(chunks)
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
                "x-maxPages": MAX_PDF_PAGES,
            },
        ),
    ],
    pipeline: PolicyPipelineDep,
    sessions: PortfolioSessionServiceDep,
    parsing_capacity: PdfParsingCapacityDep,
    document_id: Annotated[UUID, Form(alias="documentId")],
    password: str | None = Form(default=None),
    portfolio_session_token: str = Form(
        alias="portfolioSessionToken",
        min_length=1,
        max_length=512,
    ),
) -> PolicyParseResponse:
    data = await _read_pdf(file)
    service = PolicyUploadService(pipeline=pipeline, sessions=sessions)
    try:
        return await parsing_capacity.run(
            service.parse_policy,
            pdf_bytes=data,
            document_id=document_id.hex,
            password=password if password else None,
            portfolio_session_token=portfolio_session_token,
        )
    except PdfParsingBusyError:
        raise ApiError(
            status_code=503,
            code="PDF_PARSING_BUSY",
            message="PDF 분석 요청이 많아요. 잠시 후 다시 시도해주세요.",
        ) from None
