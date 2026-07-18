import logging
import uuid
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from app.core.middleware import REQUEST_ID_STATE_KEY

logger = logging.getLogger(__name__)


class ApiErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str


class ApiErrorResponse(BaseModel):
    error: ApiErrorDetail


class RequestValidationErrorDetail(BaseModel):
    model_config = ConfigDict(extra="allow")

    loc: list[str | int]
    msg: str
    type: str


class RequestValidationErrorResponse(BaseModel):
    detail: list[RequestValidationErrorDetail]


def api_error_responses(*status_codes: int) -> dict[int | str, dict[str, Any]]:
    """Describe application errors without changing FastAPI validation errors."""

    return {
        status_code: {
            "model": (
                ApiErrorResponse | RequestValidationErrorResponse
                if status_code == 422
                else ApiErrorResponse
            ),
            "description": "Coverly API error",
        }
        for status_code in status_codes
    }


class ApiError(Exception):
    def __init__(self, *, status_code: int, code: str, message: str) -> None:
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
