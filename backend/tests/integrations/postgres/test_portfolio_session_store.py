from contextlib import AbstractContextManager
from types import TracebackType
from typing import Any, cast

from app.integrations.postgres.portfolio_session_store import PgPortfolioSessionRepository


class _Result:
    def __init__(
        self,
        *,
        one: dict[str, object] | None = None,
        many: list[dict[str, object]] | None = None,
    ) -> None:
        self._one = one
        self._many = many or []

    def fetchone(self) -> dict[str, object] | None:
        return self._one

    def fetchall(self) -> list[dict[str, object]]:
        return self._many


class _Connection:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def __enter__(self) -> "_Connection":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    def execute(self, query: str, params: object = None) -> _Result:
        normalized = " ".join(query.split())
        self.queries.append(normalized)
        if normalized.startswith("SELECT id FROM private.portfolio_sessions"):
            return _Result(one={"id": "session-1"})
        if normalized.startswith("SELECT rag_session_id FROM private.policy_documents"):
            return _Result(many=[{"rag_session_id": "rag-1"}])
        if normalized.startswith("DELETE FROM private.portfolio_sessions"):
            return _Result(one={"id": "session-1"})
        raise AssertionError(f"Unexpected query: {normalized}")


class _Pool:
    def __init__(self, connection: _Connection) -> None:
        self._connection = connection

    def connection(self) -> AbstractContextManager[_Connection]:
        return self._connection


def test_delete_locks_session_before_collecting_rag_documents() -> None:
    connection = _Connection()
    repository = object.__new__(PgPortfolioSessionRepository)
    repository._pool = cast(Any, _Pool(connection))

    deleted_rag_ids = repository.delete("session-1")

    assert deleted_rag_ids == ("rag-1",)
    assert connection.queries[0].endswith("FOR UPDATE")
    assert connection.queries[1].startswith("SELECT rag_session_id FROM private.policy_documents")
