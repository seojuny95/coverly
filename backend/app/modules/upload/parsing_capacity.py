"""Queued admission control for CPU-heavy policy PDF parsing."""

import asyncio
from collections.abc import Awaitable, Callable
from functools import lru_cache
from typing import TypeVar

from app.core.config import get_settings

_R = TypeVar("_R")


class PdfParsingUnavailableError(Exception):
    """The bounded parser queue cannot accept or start more work."""


class PdfParsingQueueFullError(PdfParsingUnavailableError):
    """The active parser slots and bounded waiting queue are occupied."""


class PdfParsingQueueTimeoutError(PdfParsingUnavailableError):
    """The request waited too long for a parser slot."""


class PdfParsingCapacity:
    """Bound active PDF parsing and the number of requests waiting for it."""

    def __init__(
        self,
        *,
        concurrency_limit: int,
        queue_limit: int,
        queue_timeout_seconds: float,
    ) -> None:
        if concurrency_limit < 1:
            raise ValueError("PDF parsing capacity must be positive")
        if queue_limit < 0:
            raise ValueError("PDF parsing queue capacity cannot be negative")
        if queue_timeout_seconds <= 0:
            raise ValueError("PDF parsing queue timeout must be positive")

        self._slots = asyncio.Semaphore(concurrency_limit)
        self._admission_limit = concurrency_limit + queue_limit
        self._queue_timeout_seconds = queue_timeout_seconds
        self._admitted = 0

    async def run(self, operation: Callable[[], Awaitable[_R]]) -> _R:
        if self._admitted >= self._admission_limit:
            raise PdfParsingQueueFullError
        self._admitted += 1

        try:
            await asyncio.wait_for(
                self._slots.acquire(),
                timeout=self._queue_timeout_seconds,
            )
        except TimeoutError:
            self._admitted -= 1
            raise PdfParsingQueueTimeoutError from None
        except BaseException:
            self._admitted -= 1
            raise

        async def invoke() -> _R:
            return await operation()

        task = asyncio.create_task(invoke())

        def release_slot(completed: asyncio.Task[_R]) -> None:
            try:
                completed.exception()
            except asyncio.CancelledError:
                pass
            finally:
                self._slots.release()
                self._admitted -= 1

        task.add_done_callback(release_slot)
        return await asyncio.shield(task)


@lru_cache
def get_pdf_parsing_capacity() -> PdfParsingCapacity:
    settings = get_settings()
    return PdfParsingCapacity(
        concurrency_limit=settings.pdf_parsing_max_concurrency,
        queue_limit=settings.pdf_parsing_max_queue_size,
        queue_timeout_seconds=settings.pdf_parsing_queue_timeout_seconds,
    )
