"""ASGI request-size guard for the PDF multipart endpoint."""

from __future__ import annotations

import tempfile
import uuid
from collections.abc import Awaitable, Callable
from typing import Protocol

from starlette.responses import JSONResponse
from starlette.types import Message, Receive, Scope, Send

from app.core.limits import MAX_PDF_BYTES, MAX_PDF_UPLOAD_REQUEST_BYTES
from app.core.middleware import REQUEST_ID_STATE_KEY

_REPLAY_CHUNK_SIZE = 1024 * 1024
_SPOOL_MEMORY_LIMIT = 1024 * 1024

type AsgiApp = Callable[[Scope, Receive, Send], Awaitable[None]]


class _ReadableBody(Protocol):
    def read(self, size: int = -1) -> bytes: ...


class UploadRequestSizeLimitMiddleware:
    """Reject oversized uploads before Starlette parses the multipart body."""

    def __init__(
        self,
        app: AsgiApp,
        *,
        max_request_bytes: int = MAX_PDF_UPLOAD_REQUEST_BYTES,
    ) -> None:
        self._app = app
        self._max_request_bytes = max_request_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not _is_pdf_upload(scope):
            await self._app(scope, receive, send)
            return

        content_length = _content_length(scope)
        if content_length is not None:
            if content_length > self._max_request_bytes:
                await self._send_too_large(scope, receive, send)
                return
            await self._app(scope, receive, send)
            return

        with tempfile.SpooledTemporaryFile(max_size=_SPOOL_MEMORY_LIMIT) as body:
            total_bytes = 0
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                if message["type"] != "http.request":
                    continue

                chunk = message.get("body", b"")
                total_bytes += len(chunk)
                if total_bytes > self._max_request_bytes:
                    await self._send_too_large(scope, receive, send)
                    return
                body.write(chunk)
                if not message.get("more_body", False):
                    break

            body.seek(0)
            replay_receive = _body_replay_receive(body, total_bytes)
            await self._app(scope, replay_receive, send)

    async def _send_too_large(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        request_id = _request_id(scope)
        response = JSONResponse(
            status_code=413,
            headers={"x-request-id": request_id},
            content={
                "error": {
                    "code": "PDF_TOO_LARGE",
                    "message": (
                        "파일이 너무 커요. PDF 한 개당 "
                        f"{MAX_PDF_BYTES // (1024 * 1024)}MB까지 올릴 수 있어요."
                    ),
                    "request_id": request_id,
                }
            },
        )
        await response(scope, receive, send)


def _is_pdf_upload(scope: Scope) -> bool:
    return (
        scope["type"] == "http"
        and scope.get("method") == "POST"
        and scope.get("path") == "/policies/parse"
    )


def _content_length(scope: Scope) -> int | None:
    if any(name.lower() == b"transfer-encoding" for name, _value in scope.get("headers", [])):
        return None

    values: list[int] = []
    for name, raw_value in scope.get("headers", []):
        if name.lower() != b"content-length":
            continue
        try:
            value = int(raw_value)
        except ValueError:
            return None
        if value < 0:
            return None
        values.append(value)
    return max(values, default=None)


def _request_id(scope: Scope) -> str:
    state = scope.setdefault("state", {})
    value = state.get(REQUEST_ID_STATE_KEY)
    if isinstance(value, str):
        return value

    generated = str(uuid.uuid4())
    state[REQUEST_ID_STATE_KEY] = generated
    return generated


def _body_replay_receive(
    body: _ReadableBody,
    total_bytes: int,
) -> Receive:
    sent_bytes = 0
    finished = False

    async def receive() -> Message:
        nonlocal sent_bytes, finished
        if finished:
            return {"type": "http.disconnect"}

        chunk = body.read(_REPLAY_CHUNK_SIZE)
        sent_bytes += len(chunk)
        more_body = sent_bytes < total_bytes
        if not more_body:
            finished = True
        return {
            "type": "http.request",
            "body": chunk,
            "more_body": more_body,
        }

    return receive
