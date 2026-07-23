import asyncio
from collections.abc import Awaitable, Callable

import pytest

from app.core.limits import MAX_PORTFOLIO_DOCUMENTS
from app.modules.upload.parsing_capacity import (
    PdfParsingCapacity,
    PdfParsingQueueFullError,
    PdfParsingQueueTimeoutError,
)


def _operation_at(
    index: int,
    *,
    entered: list[asyncio.Event],
    release: asyncio.Event,
) -> Callable[[], Awaitable[int]]:
    async def operation() -> int:
        entered[index].set()
        await release.wait()
        return index

    return operation


def test_five_document_batch_is_admitted_with_lower_parser_concurrency() -> None:
    async def run_scenario() -> None:
        concurrency_limit = 2
        capacity = PdfParsingCapacity(
            concurrency_limit=concurrency_limit,
            queue_limit=MAX_PORTFOLIO_DOCUMENTS - concurrency_limit,
            queue_timeout_seconds=1,
        )
        entered = [asyncio.Event() for _ in range(MAX_PORTFOLIO_DOCUMENTS)]
        release = asyncio.Event()

        admitted = [
            asyncio.create_task(
                capacity.run(_operation_at(index, entered=entered, release=release))
            )
            for index in range(MAX_PORTFOLIO_DOCUMENTS)
        ]
        await asyncio.gather(*(event.wait() for event in entered[:concurrency_limit]))
        await asyncio.sleep(0)

        with pytest.raises(PdfParsingQueueFullError):
            await capacity.run(lambda: asyncio.sleep(0))

        release.set()
        assert await asyncio.gather(*admitted) == list(range(MAX_PORTFOLIO_DOCUMENTS))

    asyncio.run(run_scenario())


def test_queued_work_times_out_and_releases_its_admission_slot() -> None:
    async def run_scenario() -> None:
        capacity = PdfParsingCapacity(
            concurrency_limit=1,
            queue_limit=1,
            queue_timeout_seconds=0.01,
        )
        entered = [asyncio.Event(), asyncio.Event()]
        release = asyncio.Event()
        active = asyncio.create_task(
            capacity.run(_operation_at(0, entered=entered, release=release))
        )
        await entered[0].wait()

        with pytest.raises(PdfParsingQueueTimeoutError):
            await capacity.run(_operation_at(1, entered=entered, release=release))

        release.set()
        assert await active == 0
        assert await capacity.run(lambda: asyncio.sleep(0, result=2)) == 2

    asyncio.run(run_scenario())


def test_cancelled_waiter_releases_its_admission_slot() -> None:
    async def run_scenario() -> None:
        capacity = PdfParsingCapacity(
            concurrency_limit=1,
            queue_limit=1,
            queue_timeout_seconds=1,
        )
        entered = [asyncio.Event(), asyncio.Event()]
        release = asyncio.Event()
        active = asyncio.create_task(
            capacity.run(_operation_at(0, entered=entered, release=release))
        )
        await entered[0].wait()

        cancelled = asyncio.create_task(
            capacity.run(_operation_at(1, entered=entered, release=release))
        )
        await asyncio.sleep(0)
        cancelled.cancel()
        with pytest.raises(asyncio.CancelledError):
            await cancelled

        replacement = asyncio.create_task(
            capacity.run(_operation_at(1, entered=entered, release=release))
        )
        await asyncio.sleep(0)
        assert not replacement.done()

        release.set()
        assert await active == 0
        assert await replacement == 1

    asyncio.run(run_scenario())


def test_cancelled_active_request_keeps_slot_until_operation_finishes() -> None:
    async def run_scenario() -> None:
        capacity = PdfParsingCapacity(
            concurrency_limit=1,
            queue_limit=1,
            queue_timeout_seconds=1,
        )
        entered = [asyncio.Event(), asyncio.Event()]
        release = asyncio.Event()
        active = asyncio.create_task(
            capacity.run(_operation_at(0, entered=entered, release=release))
        )
        await entered[0].wait()

        active.cancel()
        with pytest.raises(asyncio.CancelledError):
            await active

        queued = asyncio.create_task(
            capacity.run(_operation_at(1, entered=entered, release=release))
        )
        await asyncio.sleep(0)
        with pytest.raises(PdfParsingQueueFullError):
            await capacity.run(lambda: asyncio.sleep(0))

        release.set()
        assert await queued == 1

    asyncio.run(run_scenario())


def test_failed_operation_releases_parser_and_admission_slots() -> None:
    async def run_scenario() -> None:
        capacity = PdfParsingCapacity(
            concurrency_limit=1,
            queue_limit=0,
            queue_timeout_seconds=1,
        )

        async def fail() -> None:
            raise RuntimeError("parse failed")

        with pytest.raises(RuntimeError, match="parse failed"):
            await capacity.run(fail)

        assert await capacity.run(lambda: asyncio.sleep(0, result="recovered")) == "recovered"

    asyncio.run(run_scenario())
