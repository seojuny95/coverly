"""FastAPI dependency wiring for portfolio sessions."""

from typing import Annotated

from fastapi import Depends

from app.core.config import get_settings
from app.core.errors import ApiError
from app.modules.portfolio.session.service import (
    PortfolioSessionService,
    shared_portfolio_session_service,
)


def get_portfolio_session_service() -> PortfolioSessionService:
    if not get_settings().database_url:
        raise _unavailable_error()
    try:
        return shared_portfolio_session_service()
    except RuntimeError as exc:
        raise _unavailable_error() from exc


def _unavailable_error() -> ApiError:
    return ApiError(
        status_code=503,
        code="portfolio_session_unavailable",
        message="분석 세션을 준비하지 못했어요. 잠시 후 다시 시도해주세요.",
    )


PortfolioSessionServiceDep = Annotated[
    PortfolioSessionService,
    Depends(get_portfolio_session_service),
]
