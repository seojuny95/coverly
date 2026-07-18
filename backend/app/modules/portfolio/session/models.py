"""Domain models for short-lived portfolio sessions."""

from dataclasses import dataclass
from datetime import datetime

from app.modules.portfolio.schemas import PolicyInput


@dataclass(frozen=True)
class NewPortfolioSession:
    id: str
    created_at: datetime
    expires_at: datetime
    max_expires_at: datetime


@dataclass(frozen=True)
class StoredPolicyDocument:
    id: str
    policy: PolicyInput
    rag_session_id: str | None


@dataclass(frozen=True)
class PolicyDocumentReservation:
    session_id: str
    document_id: str


@dataclass(frozen=True)
class PortfolioSessionSnapshot:
    session_id: str
    version: int
    policies: tuple[PolicyInput, ...]
    rag_session_ids: tuple[str, ...]


@dataclass(frozen=True)
class CachedPortfolioAnalysis:
    version: int
    context_hash: str
    result: dict[str, object]
