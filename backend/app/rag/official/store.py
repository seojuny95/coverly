"""Storage contract for official-source RAG vectors."""

from typing import Protocol

from app.rag.official.models import RetrievalHit, VectorRecord


class OfficialRagStore(Protocol):
    def replace_all(self, records: tuple[VectorRecord, ...]) -> None: ...

    def query(
        self,
        *,
        query_embedding: tuple[float, ...],
        query_text: str,
        top_k: int,
    ) -> list[RetrievalHit]: ...
