"""HTTP middleware shared by all API modules."""

import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response

REQUEST_ID_STATE_KEY = "request_id"


async def request_id_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    setattr(request.state, REQUEST_ID_STATE_KEY, request_id)

    response = await call_next(request)
    response.headers["x-request-id"] = request_id
    return response
