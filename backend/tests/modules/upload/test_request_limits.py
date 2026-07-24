"""Transport-level PDF upload request-size tests."""

import json
from collections.abc import Awaitable, Callable
from typing import Any, cast
from uuid import UUID

from starlette.types import Message, Receive, Scope, Send

from app.modules.upload.request_limits import UploadRequestSizeLimitMiddleware

type AsgiApp = Callable[[Scope, Receive, Send], Awaitable[None]]


def test_content_length_rejects_before_the_downstream_app_reads() -> None:
    downstream_called = False

    async def downstream(_scope: Scope, _receive: Receive, _send: Send) -> None:
        nonlocal downstream_called
        downstream_called = True

    middleware = UploadRequestSizeLimitMiddleware(
        cast(AsgiApp, downstream),
        max_request_bytes=8,
    )
    response = _invoke(
        middleware,
        headers=[(b"content-length", b"9")],
        messages=[],
    )

    assert downstream_called is False
    assert response["status"] == 413
    payload = json.loads(cast(bytes, response["body"]))
    UUID(payload["error"]["request_id"])
    assert payload["error"]["code"] == "PDF_TOO_LARGE"


def test_conflicting_content_lengths_use_the_largest_declared_size() -> None:
    downstream_called = False

    async def downstream(_scope: Scope, _receive: Receive, _send: Send) -> None:
        nonlocal downstream_called
        downstream_called = True

    middleware = UploadRequestSizeLimitMiddleware(
        cast(AsgiApp, downstream),
        max_request_bytes=8,
    )
    response = _invoke(
        middleware,
        headers=[(b"content-length", b"1"), (b"content-length", b"9")],
        messages=[],
    )

    assert downstream_called is False
    assert response["status"] == 413


def test_chunked_body_is_bounded_and_never_reaches_multipart_parsing() -> None:
    downstream_called = False

    async def downstream(_scope: Scope, _receive: Receive, _send: Send) -> None:
        nonlocal downstream_called
        downstream_called = True

    middleware = UploadRequestSizeLimitMiddleware(
        cast(AsgiApp, downstream),
        max_request_bytes=8,
    )
    response = _invoke(
        middleware,
        headers=[(b"transfer-encoding", b"chunked")],
        messages=[
            {"type": "http.request", "body": b"12345", "more_body": True},
            {"type": "http.request", "body": b"6789", "more_body": False},
        ],
    )

    assert downstream_called is False
    assert response["status"] == 413


def test_chunked_body_is_replayed_without_changing_bytes() -> None:
    downstream_body = bytearray()

    async def downstream(_scope: Scope, receive: Receive, send: Send) -> None:
        while True:
            message = await receive()
            if message["type"] != "http.request":
                break
            downstream_body.extend(message.get("body", b""))
            if not message.get("more_body", False):
                break
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = UploadRequestSizeLimitMiddleware(
        cast(AsgiApp, downstream),
        max_request_bytes=8,
    )
    response = _invoke(
        middleware,
        headers=[],
        messages=[
            {"type": "http.request", "body": b"123", "more_body": True},
            {"type": "http.request", "body": b"456", "more_body": False},
        ],
    )

    assert response["status"] == 204
    assert downstream_body == b"123456"


def _invoke(
    app: UploadRequestSizeLimitMiddleware,
    *,
    headers: list[tuple[bytes, bytes]],
    messages: list[Message],
) -> dict[str, Any]:
    sent: list[Message] = []
    pending = list(messages)

    async def receive() -> Message:
        if pending:
            return pending.pop(0)
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        sent.append(message)

    async def run() -> None:
        await app(
            cast(
                Scope,
                {
                    "type": "http",
                    "asgi": {"version": "3.0"},
                    "http_version": "1.1",
                    "method": "POST",
                    "scheme": "http",
                    "path": "/policies/parse",
                    "raw_path": b"/policies/parse",
                    "query_string": b"",
                    "headers": headers,
                    "client": ("127.0.0.1", 1),
                    "server": ("test", 80),
                    "state": {},
                },
            ),
            receive,
            send,
        )

    import asyncio

    asyncio.run(run())
    start = next(message for message in sent if message["type"] == "http.response.start")
    body = b"".join(
        cast(bytes, message.get("body", b""))
        for message in sent
        if message["type"] == "http.response.body"
    )
    return {"status": start["status"], "body": body}
