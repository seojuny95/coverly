from types import TracebackType
from typing import Any

import psycopg
from pytest import MonkeyPatch

from app.integrations.postgres import premium_benchmark_store as subject


class _Cursor:
    def fetchone(self) -> None:
        return None

    def fetchall(self) -> list[dict[str, Any]]:
        return []


class _Connection:
    def __enter__(self) -> "_Connection":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    def execute(self, query: object, params: object = None) -> _Cursor:
        return _Cursor()


def test_postgres_benchmark_queries_use_bounded_connect_timeout(
    monkeypatch: MonkeyPatch,
) -> None:
    connect_calls: list[dict[str, object]] = []

    def connect(database_url: str, **kwargs: object) -> _Connection:
        assert database_url == "postgresql://example/test"
        connect_calls.append(kwargs)
        return _Connection()

    monkeypatch.setattr(psycopg, "connect", connect)
    repository = subject.PostgresPremiumBenchmarkRepository(
        "postgresql://example/test",
        schema="reference",
        benchmark_table="premium_burden_guides",
        source_table="sources",
    )

    assert repository.find_by_age(35) is None
    assert repository.list_all() == ()
    assert [call["connect_timeout"] for call in connect_calls] == [3, 3]
