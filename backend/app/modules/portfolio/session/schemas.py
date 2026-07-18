"""HTTP contracts for portfolio session lifecycle operations."""

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
    status: str
