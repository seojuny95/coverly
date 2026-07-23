"""Admission control for CPU-heavy policy PDF parsing."""

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from functools import lru_cache
from threading import BoundedSemaphore
from typing import ParamSpec, TypeVar

MAX_CONCURRENT_PDF_PARSING = 2
MAX_CONCURRENT_PDF_BUFFERS = 2

_P = ParamSpec("_P")
_R = TypeVar("_R")


class PdfParsingBusyError(Exception):
    """All policy parsing workers are currently occupied."""


class PdfBufferCapacity:
    """Bound requests that retain a complete PDF byte buffer."""

    def __init__(self, limit: int) -> None:
        if limit < 1:
            raise ValueError("PDF buffer capacity must be positive")
        self._slots = BoundedSemaphore(limit)

    @asynccontextmanager
    async def reserve(self) -> AsyncIterator[None]:
        if not self._slots.acquire(blocking=False):
            raise PdfParsingBusyError
        try:
            yield
        finally:
            self._slots.release()


class PdfParsingCapacity:
    """Run parsing work without allowing an unbounded waiting queue."""

    def __init__(self, limit: int) -> None:
        if limit < 1:
            raise ValueError("PDF parsing capacity must be positive")
        self._slots = BoundedSemaphore(limit)

    async def run(
        self,
        operation: Callable[_P, _R],
        *args: _P.args,
        **kwargs: _P.kwargs,
    ) -> _R:
        if not self._slots.acquire(blocking=False):
            raise PdfParsingBusyError

        task = asyncio.create_task(asyncio.to_thread(operation, *args, **kwargs))

        def release_slot(completed: asyncio.Task[_R]) -> None:
            try:
                completed.exception()
            except asyncio.CancelledError:
                pass
            finally:
                self._slots.release()

        task.add_done_callback(release_slot)
        return await asyncio.shield(task)


@lru_cache
def get_pdf_parsing_capacity() -> PdfParsingCapacity:
    return PdfParsingCapacity(MAX_CONCURRENT_PDF_PARSING)


@lru_cache
def get_pdf_buffer_capacity() -> PdfBufferCapacity:
    return PdfBufferCapacity(MAX_CONCURRENT_PDF_BUFFERS)
