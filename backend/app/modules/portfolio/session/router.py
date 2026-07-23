"""HTTP boundary for one-token portfolio sessions."""

from fastapi import APIRouter

from app.core.config import get_settings
from app.core.errors import api_error_responses
from app.modules.portfolio.session.dependencies import PortfolioSessionServiceDep
from app.modules.portfolio.session.http import expired_portfolio_session_error
from app.modules.portfolio.session.schemas import (
    PortfolioSessionDeleteResponse,
    PortfolioSessionDocumentsDeleteRequest,
    PortfolioSessionRequest,
    PortfolioSessionResponse,
)
from app.modules.portfolio.session.service import (
    InvalidPortfolioSessionToken,
)

router = APIRouter(prefix="/portfolio/sessions", tags=["portfolio-sessions"])


@router.post(
    "",
    response_model=PortfolioSessionResponse,
    responses=api_error_responses(503),
)
def create_portfolio_session(
    sessions: PortfolioSessionServiceDep,
) -> PortfolioSessionResponse:
    access = sessions.create()
    return PortfolioSessionResponse(
        portfolio_session_token=access.token,
        expires_at=access.expires_at.isoformat(),
        counsel_turns_remaining=get_settings().counsel_max_turns_per_session,
    )


@router.post(
    "/refresh",
    response_model=PortfolioSessionResponse,
    responses=api_error_responses(403, 503),
)
def refresh_portfolio_session(
    request: PortfolioSessionRequest,
    sessions: PortfolioSessionServiceDep,
) -> PortfolioSessionResponse:
    max_turns = get_settings().counsel_max_turns_per_session
    try:
        access = sessions.refresh(request.portfolio_session_token)
        counsel_turns_remaining = sessions.counsel_turns_remaining(
            access.token,
            max_turns=max_turns,
        )
    except InvalidPortfolioSessionToken:
        raise expired_portfolio_session_error() from None
    return PortfolioSessionResponse(
        portfolio_session_token=access.token,
        expires_at=access.expires_at.isoformat(),
        counsel_turns_remaining=counsel_turns_remaining,
    )


@router.post(
    "/delete",
    response_model=PortfolioSessionDeleteResponse,
    responses=api_error_responses(403, 503),
)
def delete_portfolio_session(
    request: PortfolioSessionRequest,
    sessions: PortfolioSessionServiceDep,
) -> PortfolioSessionDeleteResponse:
    try:
        sessions.delete(request.portfolio_session_token)
    except InvalidPortfolioSessionToken:
        raise expired_portfolio_session_error() from None
    return PortfolioSessionDeleteResponse(status="deleted")


@router.post(
    "/documents/delete",
    response_model=PortfolioSessionDeleteResponse,
    responses=api_error_responses(403, 503),
)
def delete_portfolio_session_documents(
    request: PortfolioSessionDocumentsDeleteRequest,
    sessions: PortfolioSessionServiceDep,
) -> PortfolioSessionDeleteResponse:
    try:
        sessions.delete_documents(
            request.portfolio_session_token,
            request.document_id_strings(),
        )
    except InvalidPortfolioSessionToken:
        raise expired_portfolio_session_error() from None
    return PortfolioSessionDeleteResponse(status="deleted")
