"""HTTP boundary for one-token portfolio sessions."""

from fastapi import APIRouter

from app.modules.portfolio.session.dependencies import PortfolioSessionServiceDep
from app.modules.portfolio.session.http import expired_portfolio_session_error
from app.modules.portfolio.session.schemas import (
    PortfolioSessionDeleteResponse,
    PortfolioSessionRequest,
    PortfolioSessionResponse,
)
from app.modules.portfolio.session.service import (
    InvalidPortfolioSessionToken,
)

router = APIRouter(prefix="/portfolio/sessions", tags=["portfolio-sessions"])


@router.post("", response_model=PortfolioSessionResponse)
def create_portfolio_session(
    sessions: PortfolioSessionServiceDep,
) -> PortfolioSessionResponse:
    access = sessions.create()
    return PortfolioSessionResponse(
        portfolio_session_token=access.token,
        expires_at=access.expires_at.isoformat(),
    )


@router.post("/refresh", response_model=PortfolioSessionResponse)
def refresh_portfolio_session(
    request: PortfolioSessionRequest,
    sessions: PortfolioSessionServiceDep,
) -> PortfolioSessionResponse:
    try:
        access = sessions.refresh(request.portfolio_session_token)
    except InvalidPortfolioSessionToken:
        raise expired_portfolio_session_error() from None
    return PortfolioSessionResponse(
        portfolio_session_token=access.token,
        expires_at=access.expires_at.isoformat(),
    )


@router.post("/delete", response_model=PortfolioSessionDeleteResponse)
def delete_portfolio_session(
    request: PortfolioSessionRequest,
    sessions: PortfolioSessionServiceDep,
) -> PortfolioSessionDeleteResponse:
    try:
        sessions.delete(request.portfolio_session_token)
    except InvalidPortfolioSessionToken:
        raise expired_portfolio_session_error() from None
    return PortfolioSessionDeleteResponse(status="deleted")
