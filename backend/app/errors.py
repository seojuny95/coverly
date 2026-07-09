import logging
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

REQUEST_ID_STATE_KEY = "request_id"


class ApiError(Exception):
    def __init__(self, *, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


async def request_id_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    setattr(request.state, REQUEST_ID_STATE_KEY, request_id)
    response = await call_next(request)
    response.headers["x-request-id"] = request_id
    return response


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
