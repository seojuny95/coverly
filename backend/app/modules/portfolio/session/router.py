"""HTTP boundary for one-token portfolio sessions."""

from fastapi import APIRouter

from app.core.config import get_settings
from app.core.errors import ApiError, api_error_responses
from app.modules.portfolio.sample.creation import SamplePortfolioUnavailable
from app.modules.portfolio.session.dependencies import PortfolioSessionServiceDep
from app.modules.portfolio.session.http import (
    expired_portfolio_session_error,
    portfolio_session_unavailable_error,
)
from app.modules.portfolio.session.schemas import (
    PortfolioSessionDeleteResponse,
    PortfolioSessionDocumentsDeleteRequest,
    PortfolioSessionRequest,
    PortfolioSessionResponse,
    ReadinessResponse,
    SamplePortfolioDocument,
    SamplePortfolioSessionResponse,
)
from app.modules.portfolio.session.service import (
    InvalidPortfolioSessionToken,
    PortfolioSessionReadOnly,
    PortfolioSessionUnavailable,
)

router = APIRouter(prefix="/portfolio/sessions", tags=["portfolio-sessions"])
readiness_router = APIRouter(tags=["operations"])


@readiness_router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses=api_error_responses(503),
)
def check_readiness(
    sessions: PortfolioSessionServiceDep,
) -> ReadinessResponse:
    try:
        sessions.check_ready()
    except PortfolioSessionUnavailable:
        raise portfolio_session_unavailable_error() from None
    return ReadinessResponse(status="ready")


@router.post(
    "",
    response_model=PortfolioSessionResponse,
    responses=api_error_responses(503),
)
def create_portfolio_session(
    sessions: PortfolioSessionServiceDep,
) -> PortfolioSessionResponse:
    try:
        access = sessions.create()
    except PortfolioSessionUnavailable:
        raise portfolio_session_unavailable_error() from None
    return PortfolioSessionResponse(
        portfolio_session_token=access.token,
        expires_at=access.expires_at.isoformat(),
        counsel_turns_remaining=get_settings().counsel_max_turns_per_session,
        portfolio_kind=access.kind,
    )


@router.post(
    "/sample",
    response_model=SamplePortfolioSessionResponse,
    responses=api_error_responses(503),
)
def create_sample_portfolio_session(
    sessions: PortfolioSessionServiceDep,
) -> SamplePortfolioSessionResponse:
    try:
        access, documents = sessions.create_sample()
    except (PortfolioSessionUnavailable, SamplePortfolioUnavailable):
        raise ApiError(
            status_code=503,
            code="sample_portfolio_unavailable",
            message="샘플 분석을 준비하지 못했어요. 잠시 후 다시 시도해주세요.",
        ) from None
    return SamplePortfolioSessionResponse(
        portfolio_session_token=access.token,
        expires_at=access.expires_at.isoformat(),
        counsel_turns_remaining=get_settings().counsel_max_turns_per_session,
        portfolio_kind=access.kind,
        insurance_documents=[
            SamplePortfolioDocument(file_name=file_name, result=result)
            for file_name, result in documents
        ],
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
    except PortfolioSessionUnavailable:
        raise portfolio_session_unavailable_error() from None
    return PortfolioSessionResponse(
        portfolio_session_token=access.token,
        expires_at=access.expires_at.isoformat(),
        counsel_turns_remaining=counsel_turns_remaining,
        portfolio_kind=access.kind,
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
    except PortfolioSessionUnavailable:
        raise portfolio_session_unavailable_error() from None
    return PortfolioSessionDeleteResponse(status="deleted")


@router.post(
    "/documents/delete",
    response_model=PortfolioSessionDeleteResponse,
    responses=api_error_responses(403, 409, 503),
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
    except PortfolioSessionReadOnly:
        raise ApiError(
            status_code=409,
            code="sample_portfolio_read_only",
            message="샘플 보험은 개별 증권을 변경할 수 없어요.",
        ) from None
    except PortfolioSessionUnavailable:
        raise portfolio_session_unavailable_error() from None
    return PortfolioSessionDeleteResponse(status="deleted")
