"""The SSE response must close its body iterator when the client disconnects."""

import asyncio
from collections.abc import AsyncGenerator

from starlette.types import Message, Scope

from app.core.streaming import ClosingStreamingResponse

_SCOPE: Scope = {
    "type": "http",
    "asgi": {"version": "3.0", "spec_version": "2.3"},
    "method": "GET",
    "path": "/qa/stream",
    "headers": [],
}


def test_disconnect_closes_the_body_iterator_before_the_response_returns() -> None:
    # Starlette only cancels the streaming task on disconnect, which leaves a
    # generator suspended at its yield: its finally block would then run at
    # garbage collection time. Cleanup that refunds a counsel turn cannot
    # depend on that.
    #
    # The generator below has no await of its own, so it is parked exactly at
    # the yield while the send below is in flight -- the case Starlette alone
    # does not clean up.
    cleaned_up = asyncio.Event()

    async def body() -> AsyncGenerator[str, None]:
        try:
            while True:
                yield "data: tick\n\n"
        finally:
            cleaned_up.set()

    async def scenario() -> None:
        response = ClosingStreamingResponse(body(), media_type="text/event-stream")
        client_gone = asyncio.Event()

        async def receive() -> Message:
            await client_gone.wait()
            return {"type": "http.disconnect"}

        async def send(message: Message) -> None:
            if message["type"] != "http.response.body":
                return
            # A client that goes away instead of accepting the chunk.
            client_gone.set()
            await asyncio.sleep(3600)

        await response(_SCOPE, receive, send)

        assert cleaned_up.is_set()

    asyncio.run(scenario())


def test_normal_completion_still_sends_the_whole_body() -> None:
    async def body() -> AsyncGenerator[str, None]:
        yield "data: one\n\n"
        yield "data: two\n\n"

    sent: list[Message] = []

    async def scenario() -> None:
        response = ClosingStreamingResponse(body(), media_type="text/event-stream")

        async def receive() -> Message:
            await asyncio.sleep(3600)
            raise AssertionError("unreachable")

        async def send(message: Message) -> None:
            sent.append(message)

        await response(_SCOPE, receive, send)

    asyncio.run(scenario())

    bodies = [message["body"] for message in sent if message["type"] == "http.response.body"]
    assert b"".join(bodies) == b"data: one\n\ndata: two\n\n"
