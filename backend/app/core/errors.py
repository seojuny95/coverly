import logging
import uuid
from typing import Any, Literal

from fastapi import Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.middleware import REQUEST_ID_STATE_KEY

logger = logging.getLogger(__name__)

type ApiErrorCode = Literal[
    "PDF_TOO_LARGE",
    "INVALID_PDF",
    "PDF_PASSWORD_REQUIRED",
    "PDF_PASSWORD_INCORRECT",
    "PDF_TEXT_EXTRACTION_FAILED",
    "reference_data_unavailable",
    "INVALID_PORTFOLIO_SESSION",
    "PORTFOLIO_DOCUMENT_LIMIT_EXCEEDED",
    "COUNSEL_TURN_LIMIT_REACHED",
    "POLICY_UPLOAD_CANCELLED",
    "portfolio_session_unavailable",
    "INVALID_POLICY_SELECTION",
    "REQUEST_VALIDATION_ERROR",
    "INVALID_MULTIPART_REQUEST",
]


class ApiErrorDetail(BaseModel):
    code: ApiErrorCode
    message: str
    request_id: str


class ApiErrorResponse(BaseModel):
    error: ApiErrorDetail


def api_error_responses(
    *status_codes: int,
    response_media_type: str | None = None,
) -> dict[int | str, dict[str, Any]]:
    """Describe every route error with the shared public envelope."""

    described_status_codes = dict.fromkeys((*status_codes, 422))

    if response_media_type is not None:
        return {
            status_code: {
                "description": "Coverly API error",
                "content": {
                    response_media_type: {
                        "schema": {"$ref": "#/components/schemas/ApiErrorResponse"}
                    }
                },
            }
            for status_code in described_status_codes
        }

    return {
        status_code: {
            "model": ApiErrorResponse,
            "description": "Coverly API error",
        }
        for status_code in described_status_codes
    }


class ApiError(Exception):
    def __init__(self, *, status_code: int, code: ApiErrorCode, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


async def api_error_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, ApiError):
        raise exc

    request_id = getattr(request.state, REQUEST_ID_STATE_KEY, str(uuid.uuid4()))
    logger.info(
        "api_error",
        extra={
            "code": exc.code,
            "request_id": request_id,
            "status_code": exc.status_code,
            "path": request.url.path,
        },
    )
    return JSONResponse(
        status_code=exc.status_code,
        headers={"x-request-id": request_id},
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "request_id": request_id,
            },
        },
    )


async def request_validation_error_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        raise exc

    request_id = getattr(request.state, REQUEST_ID_STATE_KEY, str(uuid.uuid4()))
    logger.info(
        "request_validation_error",
        extra={
            "code": "REQUEST_VALIDATION_ERROR",
            "request_id": request_id,
            "status_code": 422,
            "path": request.url.path,
            "issue_count": len(exc.errors()),
        },
    )
    return JSONResponse(
        status_code=422,
        headers={"x-request-id": request_id},
        content={
            "error": {
                "code": "REQUEST_VALIDATION_ERROR",
                "message": "요청 내용을 확인해주세요.",
                "request_id": request_id,
            },
        },
    )


async def http_error_handler(request: Request, exc: Exception) -> Response:
    if not isinstance(exc, StarletteHTTPException):
        raise exc
    if exc.status_code != 400 or request.url.path != "/policies/parse":
        return await http_exception_handler(request, exc)

    request_id = getattr(request.state, REQUEST_ID_STATE_KEY, str(uuid.uuid4()))
    logger.info(
        "invalid_multipart_request",
        extra={
            "code": "INVALID_MULTIPART_REQUEST",
            "request_id": request_id,
            "status_code": 400,
            "path": request.url.path,
        },
    )
    return JSONResponse(
        status_code=400,
        headers={"x-request-id": request_id},
        content={
            "error": {
                "code": "INVALID_MULTIPART_REQUEST",
                "message": "업로드 요청 형식을 확인해주세요.",
                "request_id": request_id,
            },
        },
    )
