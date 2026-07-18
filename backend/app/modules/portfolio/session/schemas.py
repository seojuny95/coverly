"""HTTP contracts for portfolio session lifecycle operations."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class PortfolioSessionRequest(BaseModel):
    portfolio_session_token: str = Field(
        alias="portfolioSessionToken",
        min_length=1,
        max_length=512,
    )


class PortfolioSessionResponse(BaseModel):
    portfolio_session_token: str = Field(serialization_alias="portfolioSessionToken")
    expires_at: str = Field(serialization_alias="expiresAt")


class PortfolioSessionDeleteResponse(BaseModel):
    status: Literal["deleted"]


class PortfolioSessionDocumentsDeleteRequest(PortfolioSessionRequest):
    document_ids: list[UUID] = Field(
        alias="documentIds",
        min_length=1,
        max_length=50,
    )

    def document_id_strings(self) -> list[str]:
        return [document_id.hex for document_id in self.document_ids]
