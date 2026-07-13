import asyncio

from fastapi import APIRouter, UploadFile

from app.errors import ApiError
from app.services.pipeline import EmptyTextError, run_pipeline
from app.services.rag.policy import delete_policy_session

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
    try:
        result = await asyncio.to_thread(run_pipeline, data)
    except EmptyTextError:
        raise ApiError(
            status_code=422,
            code="PDF_TEXT_EXTRACTION_FAILED",
            message="PDF에서 텍스트를 추출할 수 없습니다.",
        ) from None
    return {"status": "accepted", **result}


@router.delete("/sessions/{session_id}")
def delete_policy_text_session(session_id: str) -> dict[str, str]:
    delete_policy_session(session_id)
    return {"status": "deleted"}
