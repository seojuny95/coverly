"""Storage protocol for uploaded-policy vectors."""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from app.rag.policy.models import PolicyRetrievalHit, PolicyVectorRecord


class PolicyRagStore(Protocol):
    def add(self, records: Sequence[PolicyVectorRecord]) -> None: ...

    def query(
        self,
        session_ids: Sequence[str],
        query_embedding: tuple[float, ...],
        *,
        top_k: int,
    ) -> list[PolicyRetrievalHit]: ...

    def extend(self, session_id: str, expires_at: datetime) -> bool: ...

    def delete(self, session_id: str) -> None: ...

    def delete_expired(self, now: datetime) -> int: ...
