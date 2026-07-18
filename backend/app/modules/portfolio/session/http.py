"""Shared HTTP mapping for portfolio session access."""

from app.core.errors import ApiError
from app.modules.portfolio.schemas import PortfolioSelectionInput
from app.modules.portfolio.session.models import PortfolioSessionSnapshot
from app.modules.portfolio.session.repository import PortfolioPolicySelectionNotFound
from app.modules.portfolio.session.service import (
    InvalidPortfolioSessionToken,
    PortfolioSessionService,
)


def resolve_portfolio_snapshot(
    sessions: PortfolioSessionService,
    selection: PortfolioSelectionInput,
) -> PortfolioSessionSnapshot:
    try:
        return sessions.snapshot(
            selection.portfolio_session_token,
            policy_ids=selection.policy_id_strings(),
        )
    except InvalidPortfolioSessionToken:
        raise expired_portfolio_session_error() from None
    except PortfolioPolicySelectionNotFound:
        raise ApiError(
            status_code=422,
            code="INVALID_POLICY_SELECTION",
            message="선택한 보험증권을 분석 세션에서 찾지 못했어요.",
        ) from None


def expired_portfolio_session_error() -> ApiError:
    return ApiError(
        status_code=403,
        code="INVALID_PORTFOLIO_SESSION",
        message="분석 세션이 만료됐어요. 보험증권을 다시 올려주세요.",
    )
