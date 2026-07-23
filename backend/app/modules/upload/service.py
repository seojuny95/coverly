"""Application service for policy uploads bound to a portfolio session."""

from typing import Protocol

from app.core.errors import ApiError
from app.core.limits import MAX_PORTFOLIO_DOCUMENTS
from app.modules.policy.parsing import (
    PdfComplexityLimitExceededError,
    PdfPageLimitExceededError,
    PdfPasswordIncorrectError,
    PdfPasswordRequiredError,
)
from app.modules.policy.pipeline import EmptyTextError, PipelineResult
from app.modules.policy.schemas import PolicyParseResponse
from app.modules.portfolio.session.models import PolicyDocumentReservation
from app.modules.portfolio.session.service import (
    InvalidPortfolioSessionToken,
    PortfolioSessionDocumentCancelled,
    PortfolioSessionDocumentConflict,
    PortfolioSessionDocumentLimitExceeded,
    PortfolioSessionService,
    PortfolioSessionUnavailable,
    RegisteredPolicyDocument,
)
from app.modules.reference_data.loader import ReferenceDataUnavailableError


class PolicyPipeline(Protocol):
    def __call__(self, pdf_bytes: bytes, *, password: str | None = None) -> PipelineResult: ...


type PortfolioUploadSessionError = (
    InvalidPortfolioSessionToken
    | PortfolioSessionDocumentLimitExceeded
    | PortfolioSessionDocumentCancelled
    | PortfolioSessionDocumentConflict
)


class PolicyUploadService:
    def __init__(
        self,
        *,
        pipeline: PolicyPipeline,
        sessions: PortfolioSessionService,
    ) -> None:
        self._pipeline = pipeline
        self._sessions = sessions

    def parse_policy(
        self,
        *,
        pdf_bytes: bytes,
        document_id: str,
        password: str | None,
        portfolio_session_token: str,
    ) -> PolicyParseResponse:
        reservation = self._begin_upload(portfolio_session_token, document_id)

        try:
            result = self._run_pipeline(pdf_bytes, password=password)
            document = self._complete_upload(reservation, result)
        finally:
            self._sessions.release_upload(reservation)

        return _policy_parse_response(document, result)

    def _begin_upload(
        self,
        portfolio_session_token: str,
        document_id: str,
    ) -> PolicyDocumentReservation:
        try:
            return self._sessions.begin_upload(
                portfolio_session_token,
                document_id=document_id,
            )
        except (
            InvalidPortfolioSessionToken,
            PortfolioSessionDocumentLimitExceeded,
            PortfolioSessionDocumentCancelled,
            PortfolioSessionDocumentConflict,
        ) as exc:
            raise _portfolio_session_error(exc) from None
        except PortfolioSessionUnavailable as exc:
            raise _portfolio_session_unavailable_error() from exc

    def _run_pipeline(
        self,
        pdf_bytes: bytes,
        *,
        password: str | None,
    ) -> PipelineResult:
        try:
            return self._pipeline(pdf_bytes, password=password)
        except PdfPasswordRequiredError:
            raise ApiError(
                status_code=422,
                code="PDF_PASSWORD_REQUIRED",
                message="PDF 비밀번호를 입력해주세요.",
            ) from None
        except PdfPasswordIncorrectError:
            raise ApiError(
                status_code=422,
                code="PDF_PASSWORD_INCORRECT",
                message="PDF 비밀번호가 맞지 않아요. 다시 입력해주세요.",
            ) from None
        except EmptyTextError:
            raise ApiError(
                status_code=422,
                code="PDF_TEXT_EXTRACTION_FAILED",
                message="PDF에서 텍스트를 추출할 수 없습니다.",
            ) from None
        except PdfPageLimitExceededError:
            raise ApiError(
                status_code=413,
                code="PDF_PAGE_LIMIT_EXCEEDED",
                message="분석할 수 있는 PDF 페이지 수를 초과했어요. 파일을 나눠서 올려주세요.",
            ) from None
        except PdfComplexityLimitExceededError:
            raise ApiError(
                status_code=413,
                code="PDF_COMPLEXITY_LIMIT_EXCEEDED",
                message="PDF의 텍스트나 표가 너무 많아요. 파일을 나눠서 올려주세요.",
            ) from None
        except ReferenceDataUnavailableError as exc:
            raise ApiError(
                status_code=503,
                code="reference_data_unavailable",
                message="분석 기준 정보를 불러오지 못했어요. 잠시 후 다시 시도해주세요.",
            ) from exc

    def _complete_upload(
        self,
        reservation: PolicyDocumentReservation,
        result: PipelineResult,
    ) -> RegisteredPolicyDocument:
        try:
            return self._sessions.complete_upload(reservation, result)
        except (
            InvalidPortfolioSessionToken,
            PortfolioSessionDocumentLimitExceeded,
            PortfolioSessionDocumentCancelled,
            PortfolioSessionDocumentConflict,
        ) as exc:
            raise _portfolio_session_error(exc) from None
        except PortfolioSessionUnavailable as exc:
            raise _portfolio_session_unavailable_error() from exc


def _portfolio_session_error(error: PortfolioUploadSessionError) -> ApiError:
    if isinstance(error, InvalidPortfolioSessionToken):
        return ApiError(
            status_code=403,
            code="INVALID_PORTFOLIO_SESSION",
            message="분석 세션이 만료됐어요. 보험증권을 다시 올려주세요.",
        )
    if isinstance(error, PortfolioSessionDocumentLimitExceeded):
        return ApiError(
            status_code=422,
            code="PORTFOLIO_DOCUMENT_LIMIT_EXCEEDED",
            message=f"보험증권은 최대 {MAX_PORTFOLIO_DOCUMENTS}개까지 분석할 수 있어요.",
        )
    if isinstance(error, PortfolioSessionDocumentConflict):
        return ApiError(
            status_code=409,
            code="POLICY_UPLOAD_CANCELLED",
            message="같은 문서의 업로드가 이미 진행 중이거나 완료됐어요.",
        )
    return ApiError(
        status_code=409,
        code="POLICY_UPLOAD_CANCELLED",
        message="취소된 업로드예요. 파일을 다시 선택해주세요.",
    )


def _portfolio_session_unavailable_error() -> ApiError:
    return ApiError(
        status_code=503,
        code="portfolio_session_unavailable",
        message="분석 세션을 준비하지 못했어요. 잠시 후 다시 시도해주세요.",
    )


def _policy_parse_response(
    document: RegisteredPolicyDocument,
    result: PipelineResult,
) -> PolicyParseResponse:
    client_result = dict(result)
    client_result.pop("문서세션ID", None)
    return PolicyParseResponse.model_validate(
        {
            "status": "accepted",
            "document_id": document.id,
            **client_result,
        }
    )
