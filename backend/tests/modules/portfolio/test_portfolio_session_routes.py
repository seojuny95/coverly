from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.modules.portfolio.session.dependencies import get_portfolio_session_service
from app.modules.portfolio.session.router import router
from app.modules.portfolio.session.service import PortfolioSessionAccess


class _Sessions:
    def __init__(self) -> None:
        self.refreshed: list[str] = []
        self.deleted: list[str] = []

    def create(self) -> PortfolioSessionAccess:
        return _access("created-token")

    def refresh(self, token: str) -> PortfolioSessionAccess:
        self.refreshed.append(token)
        return _access("refreshed-token")

    def delete(self, token: str) -> None:
        self.deleted.append(token)


def test_portfolio_session_lifecycle_uses_one_token_contract() -> None:
    sessions = _Sessions()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_portfolio_session_service] = lambda: sessions
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

    assert created.status_code == 200
    assert created.json()["portfolioSessionToken"] == "created-token"
    assert refreshed.json()["portfolioSessionToken"] == "refreshed-token"
    assert sessions.refreshed == ["created-token"]
    assert deleted.json() == {"status": "deleted"}
    assert sessions.deleted == ["refreshed-token"]


def _access(token: str) -> PortfolioSessionAccess:
    return PortfolioSessionAccess(
        token=token,
        expires_at=datetime(2026, 7, 18, 12, tzinfo=UTC),
    )
