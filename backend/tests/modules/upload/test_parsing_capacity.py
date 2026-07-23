import asyncio
from threading import Event

import pytest

from app.modules.upload.parsing_capacity import PdfParsingBusyError, PdfParsingCapacity


def test_parsing_capacity_rejects_work_instead_of_queueing() -> None:
    async def run_scenario() -> None:
        capacity = PdfParsingCapacity(limit=1)
        started = Event()
        finish = Event()

        def blocking_parse() -> str:
            started.set()
            finish.wait(timeout=2)
            return "parsed"

        active = asyncio.create_task(capacity.run(blocking_parse))
        assert await asyncio.to_thread(started.wait, 1)

        with pytest.raises(PdfParsingBusyError):
            await capacity.run(lambda: "queued")

        finish.set()
        assert await active == "parsed"
        assert await capacity.run(lambda: "next") == "next"

    asyncio.run(run_scenario())


def test_parsing_capacity_keeps_slot_until_cancelled_call_finishes() -> None:
    async def run_scenario() -> None:
        capacity = PdfParsingCapacity(limit=1)
        started = Event()
        finish = Event()

        def blocking_parse() -> None:
            started.set()
            finish.wait(timeout=2)

        active = asyncio.create_task(capacity.run(blocking_parse))
        assert await asyncio.to_thread(started.wait, 1)

        active.cancel()
        with pytest.raises(asyncio.CancelledError):
            await active
        with pytest.raises(PdfParsingBusyError):
            await capacity.run(lambda: None)

        finish.set()
        for _ in range(100):
            try:
                await capacity.run(lambda: None)
            except PdfParsingBusyError:
                await asyncio.sleep(0)
            else:
                break
        else:
            raise AssertionError("parsing slot was not released after worker completion")

    asyncio.run(run_scenario())
