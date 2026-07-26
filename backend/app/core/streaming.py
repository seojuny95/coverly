"""Streaming response that cleans up deterministically on client disconnect."""

from collections.abc import AsyncGenerator

import anyio
from starlette.responses import StreamingResponse
from starlette.types import Send

# Upper bound on the shielded aclose() wait below. The qa stream's cleanup
# path (_refund_counsel_turn_best_effort -> asyncio.to_thread ->
# psycopg pool checkout) has no statement timeout and a 30s default pool
# checkout timeout, so an unbounded shield would let a wedged database pin
# this request task indefinitely and block graceful shutdown on behalf of a
# client that already left. 5s is generous for the normal case -- the
# cleanup is one small UPDATE -- while keeping the worst case well under the
# pool's own 30s ceiling.
#
# This only bounds *waiting* for the cleanup, not the cleanup itself: the
# asyncio.to_thread work already submitted to the threadpool keeps running
# to completion even after move_on_after gives up on the await.
_SHIELDED_CLEANUP_TIMEOUT_SECONDS = 5.0


class ClosingStreamingResponse(StreamingResponse):
    """Close the body iterator as soon as the client goes away.

    uvicorn advertises ASGI spec_version 2.3, so Starlette streams inside an
    anyio task group and merely cancels stream_response on disconnect --
    leaving the async generator suspended at its yield. Its finally block
    would then run only at garbage collection. Closing it here makes cleanup
    (counsel-turn refund, agent cancellation) part of the request lifecycle.

    The close runs in a shielded scope because the surrounding cancel scope is
    already cancelled; an unshielded await would be cancelled immediately.
    The shield is itself time-bounded (see _SHIELDED_CLEANUP_TIMEOUT_SECONDS)
    so a slow or wedged cleanup can't pin the request task forever.
    """

    async def stream_response(self, send: Send) -> None:
        try:
            await super().stream_response(send)
        finally:
            body_iterator = self.body_iterator
            if isinstance(body_iterator, AsyncGenerator):
                with anyio.move_on_after(_SHIELDED_CLEANUP_TIMEOUT_SECONDS, shield=True):
                    await body_iterator.aclose()
