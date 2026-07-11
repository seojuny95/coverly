import asyncio

from fastapi import APIRouter, UploadFile

from app.errors import ApiError
from app.services.coverage import STATUS_OK, extract_coverages
from app.services.parsing import parse_document
from app.services.pdf_text import extract_pdf_text
from app.services.summary import extract_policy_summary
from app.services.types import Coverage

router = APIRouter(prefix="/policies", tags=["policies"])

MAX_PDF_BYTES = 10 * 1024 * 1024
_CHUNK_SIZE = 1024 * 1024


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
    text = extract_pdf_text(data)
    if not text:
        raise ApiError(
            status_code=422,
            code="PDF_TEXT_EXTRACTION_FAILED",
            message="PDF에서 텍스트를 추출할 수 없습니다.",
        )

    # 보험분류 is authoritative from the summary, so run it first. Auto policies
    # are out of Phase 1 coverage scope (their riders/rates don't fit the
    # personal-coverage model), so skip the expensive coverage extraction for them.
    summary = await asyncio.to_thread(extract_policy_summary, text)
    if summary.get("보험분류") == "자동차":
        coverages: list[Coverage] = []
        analysis_status = STATUS_OK
    else:
        # Interim double-parse (pypdf text above, pdfplumber here); the pipeline
        # task collapses both onto a single parse_document call.
        coverages, analysis_status = await asyncio.to_thread(
            lambda: extract_coverages(parse_document(data))
        )

    return {
        "status": "accepted",
        "문자수": len(text),
        "기본정보": summary,
        "보장목록": coverages,
        "분석상태": analysis_status,
    }
