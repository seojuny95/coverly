"""HTTP contracts for single-policy endpoints."""

from pydantic import BaseModel


class PolicySessionRequest(BaseModel):
    문서세션ID: str


class PolicySessionRefreshResponse(BaseModel):
    문서세션ID: str
    expiresAt: str
