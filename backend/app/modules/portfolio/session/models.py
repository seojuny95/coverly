"""Domain models for short-lived portfolio sessions."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from app.modules.portfolio.schemas import PolicyInput

PortfolioKind = Literal["uploaded", "sample"]


@dataclass(frozen=True)
class NewPortfolioSession:
    id: str
    created_at: datetime
    expires_at: datetime
    max_expires_at: datetime
    kind: PortfolioKind = "uploaded"
    version: int = 0


@dataclass(frozen=True)
class StoredPolicyDocument:
    id: str
    policy: PolicyInput
    rag_session_id: str | None


@dataclass(frozen=True)
class PolicyDocumentReservation:
    session_id: str
    document_id: str
    reservation_id: str


@dataclass(frozen=True)
class PortfolioSessionSnapshot:
    session_id: str
    version: int
    policies: tuple[PolicyInput, ...]
    rag_session_ids: tuple[str, ...]
    kind: PortfolioKind = "uploaded"


@dataclass(frozen=True)
class CachedPortfolioAnalysis:
    version: int
    context_hash: str
    result: dict[str, object]


@dataclass(frozen=True)
class ExtendedPortfolioSession:
    kind: PortfolioKind
    rag_session_ids: tuple[str, ...]
