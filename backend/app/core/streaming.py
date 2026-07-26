"""Streaming response that cleans up deterministically on client disconnect."""

from collections.abc import AsyncGenerator

import anyio
from starlette.responses import StreamingResponse
from starlette.types import Send


class ClosingStreamingResponse(StreamingResponse):
    """Close the body iterator as soon as the client goes away.

    uvicorn advertises ASGI spec_version 2.3, so Starlette streams inside an
    anyio task group and merely cancels stream_response on disconnect --
    leaving the async generator suspended at its yield. Its finally block
    would then run only at garbage collection. Closing it here makes cleanup
    (counsel-turn refund, agent cancellation) part of the request lifecycle.

    The close runs in a shielded scope because the surrounding cancel scope is
    already cancelled; an unshielded await would be cancelled immediately.
    """

    async def stream_response(self, send: Send) -> None:
        try:
            await super().stream_response(send)
        finally:
            body_iterator = self.body_iterator
            if isinstance(body_iterator, AsyncGenerator):
                with anyio.CancelScope(shield=True):
                    await body_iterator.aclose()
