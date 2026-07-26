"""The SSE response must close its body iterator when the client disconnects."""

import asyncio
from collections.abc import AsyncGenerator

import pytest
from starlette.types import Message, Scope

import app.core.streaming as streaming
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


def test_shielded_cleanup_does_not_block_past_its_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A wedged database (no statement timeout, pool checkout up to 30s) must
    # not pin the request task forever just because the cleanup await is
    # shielded from the disconnect's cancellation. Use a tiny deadline here
    # so the test stays fast; the module's real deadline is a separate,
    # deliberate operational choice.
    monkeypatch.setattr(streaming, "_SHIELDED_CLEANUP_TIMEOUT_SECONDS", 0.05)

    cleanup_started = asyncio.Event()
    cleanup_would_have_finished = asyncio.Event()

    async def body() -> AsyncGenerator[str, None]:
        try:
            while True:
                yield "data: tick\n\n"
        finally:
            cleanup_started.set()
            # Far longer than the 0.05s deadline above -- stands in for a
            # wedged DB call that never returns on its own.
            await asyncio.sleep(2.0)
            cleanup_would_have_finished.set()

    async def scenario() -> float:
        response = ClosingStreamingResponse(body(), media_type="text/event-stream")
        client_gone = asyncio.Event()

        async def receive() -> Message:
            await client_gone.wait()
            return {"type": "http.disconnect"}

        async def send(message: Message) -> None:
            if message["type"] != "http.response.body":
                return
            client_gone.set()
            await asyncio.sleep(3600)

        start = asyncio.get_running_loop().time()
        await response(_SCOPE, receive, send)
        return asyncio.get_running_loop().time() - start

    elapsed = asyncio.run(scenario())

    assert cleanup_started.is_set()
    # The wait gave up long before the 2s cleanup could finish on its own --
    # this is what proves the deadline, not just that cleanup started.
    assert not cleanup_would_have_finished.is_set()
    assert elapsed < 1.0


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
