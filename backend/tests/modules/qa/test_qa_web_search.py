import asyncio
from collections.abc import Callable, Coroutine
from threading import BoundedSemaphore, Event, Lock, Thread
from types import SimpleNamespace
from typing import Any

import pytest

from app.modules.portfolio.schemas import PolicyInput
from app.modules.qa.context import build_qa_context
from app.modules.qa.tools import web_search as subject
from app.modules.qa.tools.web_search import (
    _contains_unallowed_url,
    _search_prompt,
    _validated_source_urls,
    sanitize_search_query,
    search_allowed_domains,
)


def test_held_insurer_search_uses_only_verified_insurer_domains() -> None:
    policy = PolicyInput.model_validate(
        {
            "id": "p1",
            "기본정보": {"보험사": "삼성화재", "상품명": "건강보험"},
            "보장목록": [],
        }
    )
    context = build_qa_context("보험사 최신 안내를 찾아줘", [policy], None, [])

    assert search_allowed_domains(context, "insurer_guidance") == ["samsungfire.com"]


def test_law_update_search_uses_only_official_domains() -> None:
    context = build_qa_context("보험 법령의 최신 변경을 알려줘", [], None, [])

    assert search_allowed_domains(context, "law_update") == [
        "law.go.kr",
        "fsc.go.kr",
        "korea.kr",
        "molit.go.kr",
    ]


def test_search_query_masks_personal_identifiers() -> None:
    query = sanitize_search_query("010-1234-5678 test@example.com 계약 전 알릴 의무")

    assert "010-1234-5678" not in query
    assert "test@example.com" not in query
    assert "[전화번호]" in query
    assert "[이메일]" in query


def test_web_sources_require_cited_allowlisted_urls() -> None:
    response = {
        "output": [
            {
                "content": [
                    {
                        "annotations": [
                            {"type": "url_citation", "url": "https://www.korea.kr/one"},
                            {"type": "url_citation", "url": "https://www.molit.go.kr/two"},
                            {"type": "url_citation", "url": "https://example.com/rejected"},
                        ]
                    }
                ]
            }
        ]
    }

    assert _validated_source_urls(response, ["korea.kr", "molit.go.kr"]) == [
        "https://www.korea.kr/one",
        "https://www.molit.go.kr/two",
    ]
    assert _contains_unallowed_url("https://example.com/rejected", ["fsc.go.kr"])


def test_law_prompt_requires_source_evidence_instead_of_name_inference() -> None:
    prompt = _search_prompt("법률 별칭의 의미를 알려줘", "law_update")

    assert "공식 페이지 본문에 그 별칭이 직접 등장" in prompt
    assert "관련 없는 법률을 유추하지 마세요" in prompt


def test_official_web_search_cancels_in_flight_async_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        started = asyncio.Event()
        cancelled = asyncio.Event()

        async def blocking_search(**_kwargs: object) -> Any:
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        monkeypatch.setattr(subject, "search_official_web_async", blocking_search)
        monkeypatch.setattr(
            subject,
            "get_settings",
            lambda: SimpleNamespace(
                openai_api_key="test-key",
                openai_web_search_model="test-model",
            ),
        )
        task = asyncio.create_task(
            subject.default_official_web_search(
                "최신 안내를 알려줘",
                purpose="law_update",
                allowed_domains=["law.go.kr"],
            )
        )
        await asyncio.wait_for(started.wait(), timeout=0.1)

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert cancelled.is_set()

    asyncio.run(run())


def test_web_search_limit_is_shared_across_event_loops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _TrackingSlots:
        def __init__(self) -> None:
            self._semaphore = BoundedSemaphore(1)
            self._lock = Lock()
            self._attempts = 0
            self.second_attempted = Event()

        def acquire(self, *, blocking: bool) -> bool:
            with self._lock:
                self._attempts += 1
                if self._attempts >= 2:
                    self.second_attempted.set()
            return self._semaphore.acquire(blocking=blocking)

        def release(self) -> None:
            self._semaphore.release()

    first_acquired = Event()
    release_first = Event()
    second_acquired = Event()
    errors: list[BaseException] = []
    slots = _TrackingSlots()
    monkeypatch.setattr(subject, "_web_search_slots", slots)
    monkeypatch.setattr(subject, "_WEB_SEARCH_SLOT_POLL_SECONDS", 0.001)

    async def hold_first_slot() -> None:
        async with subject._web_search_slot():
            first_acquired.set()
            while not release_first.is_set():
                await asyncio.sleep(0.001)

    async def acquire_second_slot() -> None:
        async with subject._web_search_slot():
            second_acquired.set()

    def run_in_new_loop(operation: Callable[[], Coroutine[Any, Any, None]]) -> None:
        try:
            asyncio.run(operation())
        except BaseException as exc:
            errors.append(exc)

    first = Thread(target=run_in_new_loop, args=(hold_first_slot,), daemon=True)
    second = Thread(target=run_in_new_loop, args=(acquire_second_slot,), daemon=True)
    first.start()
    if not first_acquired.wait(timeout=1.0):
        release_first.set()
        first.join(timeout=1.0)
        pytest.fail("the first event loop did not acquire the search slot")

    second.start()
    try:
        assert slots.second_attempted.wait(timeout=1.0)
        assert not second_acquired.is_set()
    finally:
        release_first.set()
        first.join(timeout=1.0)
        second.join(timeout=1.0)

    assert second_acquired.is_set()
    assert not first.is_alive()
    assert not second.is_alive()
    assert errors == []
