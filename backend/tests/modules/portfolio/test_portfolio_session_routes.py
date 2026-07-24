from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import ApiError, api_error_handler
from app.modules.portfolio.session.dependencies import get_portfolio_session_service
from app.modules.portfolio.session.router import readiness_router, router
from app.modules.portfolio.session.service import (
    InvalidPortfolioSessionToken,
    PortfolioSessionAccess,
    PortfolioSessionUnavailable,
)


class _Sessions:
    def __init__(self) -> None:
        self.refreshed: list[str] = []
        self.deleted: list[str] = []
        self.deleted_documents: list[tuple[str, list[str]]] = []

    def check_ready(self) -> None:
        pass

    def create(self) -> PortfolioSessionAccess:
        return _access("created-token")

    def counsel_turns_remaining(self, token: str, **_kwargs: object) -> int:
        return 8

    def refresh(self, token: str) -> PortfolioSessionAccess:
        self.refreshed.append(token)
        return _access("refreshed-token")

    def delete(self, token: str) -> None:
        self.deleted.append(token)

    def delete_documents(self, token: str, document_ids: list[str]) -> None:
        self.deleted_documents.append((token, document_ids))


class _RefreshRaceSessions(_Sessions):
    def counsel_turns_remaining(self, token: str, **_kwargs: object) -> int:
        raise InvalidPortfolioSessionToken


class _UnavailableSessions(_Sessions):
    def create(self) -> PortfolioSessionAccess:
        raise PortfolioSessionUnavailable


class _NotReadySessions(_Sessions):
    def check_ready(self) -> None:
        raise PortfolioSessionUnavailable


def test_readiness_checks_the_session_store() -> None:
    ready = TestClient(_app_with_sessions(_Sessions())).get("/ready")
    unavailable = TestClient(_app_with_sessions(_NotReadySessions())).get("/ready")

    assert ready.status_code == 200
    assert ready.json() == {"status": "ready"}
    assert unavailable.status_code == 503
    assert unavailable.json()["error"]["code"] == "portfolio_session_unavailable"


def test_portfolio_session_lifecycle_uses_one_token_contract() -> None:
    sessions = _Sessions()
    app = _app_with_sessions(sessions)
    client = TestClient(app)

    created = client.post("/portfolio/sessions")
    refreshed = client.post(
        "/portfolio/sessions/refresh",
        json={"portfolioSessionToken": "created-token"},
    )
    deleted = client.post(
        "/portfolio/sessions/delete",
        json={"portfolioSessionToken": "refreshed-token"},
    )
    documents_deleted = client.post(
        "/portfolio/sessions/documents/delete",
        json={
            "portfolioSessionToken": "refreshed-token",
            "documentIds": ["00000000-0000-0000-0000-000000000001"],
        },
    )

    assert created.status_code == 200
    assert created.json()["portfolioSessionToken"] == "created-token"
    assert refreshed.json()["portfolioSessionToken"] == "refreshed-token"
    assert sessions.refreshed == ["created-token"]
    assert deleted.json() == {"status": "deleted"}
    assert sessions.deleted == ["refreshed-token"]
    assert documents_deleted.json() == {"status": "deleted"}
    assert sessions.deleted_documents == [("refreshed-token", ["00000000000000000000000000000001"])]


def test_refresh_maps_turn_lookup_race_to_expired_session() -> None:
    client = TestClient(_app_with_sessions(_RefreshRaceSessions()))

    response = client.post(
        "/portfolio/sessions/refresh",
        json={"portfolioSessionToken": "created-token"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INVALID_PORTFOLIO_SESSION"


def test_create_maps_session_store_unavailable_to_api_error() -> None:
    client = TestClient(_app_with_sessions(_UnavailableSessions()))

    response = client.post("/portfolio/sessions")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "portfolio_session_unavailable"


def _app_with_sessions(sessions: _Sessions) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(ApiError, api_error_handler)
    app.include_router(readiness_router)
    app.include_router(router)
    app.dependency_overrides[get_portfolio_session_service] = lambda: sessions
    return app


def _access(token: str) -> PortfolioSessionAccess:
    return PortfolioSessionAccess(
        token=token,
        expires_at=datetime(2026, 7, 18, 12, tzinfo=UTC),
    )
