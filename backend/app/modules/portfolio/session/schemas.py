"""HTTP contracts for portfolio session lifecycle operations."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.limits import MAX_PORTFOLIO_DOCUMENTS
from app.modules.policy.schemas import PolicyParseResponse


class ReadinessResponse(BaseModel):
    status: Literal["ready"]


class PortfolioSessionRequest(BaseModel):
    portfolio_session_token: str = Field(
        alias="portfolioSessionToken",
        min_length=1,
        max_length=512,
    )


class PortfolioSessionResponse(BaseModel):
    model_config = ConfigDict(json_schema_extra={"x-maxDocuments": MAX_PORTFOLIO_DOCUMENTS})

    portfolio_session_token: str = Field(serialization_alias="portfolioSessionToken")
    expires_at: str = Field(serialization_alias="expiresAt")
    counsel_turns_remaining: int = Field(serialization_alias="counselTurnsRemaining")
    portfolio_kind: Literal["uploaded", "sample"] = Field(serialization_alias="portfolioKind")


class SamplePortfolioDocument(BaseModel):
    file_name: str = Field(serialization_alias="fileName")
    result: PolicyParseResponse


class SamplePortfolioSessionResponse(PortfolioSessionResponse):
    insurance_documents: list[SamplePortfolioDocument] = Field(
        serialization_alias="insuranceDocuments"
    )


class PortfolioSessionDeleteResponse(BaseModel):
    status: Literal["deleted"]


class PortfolioSessionDocumentsDeleteRequest(PortfolioSessionRequest):
    document_ids: list[UUID] = Field(
        alias="documentIds",
        min_length=1,
        max_length=MAX_PORTFOLIO_DOCUMENTS,
    )

    def document_id_strings(self) -> list[str]:
        return [document_id.hex for document_id in self.document_ids]
