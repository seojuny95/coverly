"""FastAPI dependency wiring for portfolio sessions."""

from typing import Annotated

from fastapi import Depends

from app.core.config import get_settings
from app.core.errors import ApiError
from app.modules.portfolio.session.http import portfolio_session_unavailable_error
from app.modules.portfolio.session.service import (
    PortfolioSessionService,
    shared_portfolio_session_service,
)


def get_portfolio_session_service() -> PortfolioSessionService:
    if not get_settings().database_url.get_secret_value():
        raise _unavailable_error()
    try:
        return shared_portfolio_session_service()
    except RuntimeError as exc:
        raise _unavailable_error() from exc


def _unavailable_error() -> ApiError:
    return portfolio_session_unavailable_error()


PortfolioSessionServiceDep = Annotated[
    PortfolioSessionService,
    Depends(get_portfolio_session_service),
]
