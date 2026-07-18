from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import pytest

from app.modules.policy.pipeline import PipelineResult
from app.modules.portfolio.schemas import PolicyInput
from app.modules.portfolio.session.models import (
    CachedPortfolioAnalysis,
    NewPortfolioSession,
    PortfolioSessionSnapshot,
    StoredPolicyDocument,
)
from app.modules.portfolio.session.repository import AddDocumentResult
from app.modules.portfolio.session.service import (
    PortfolioSessionDocumentLimitExceeded,
    PortfolioSessionService,
)
from app.rag.policy.models import PolicyRetrievalHit, PolicyVectorRecord
from app.rag.policy.session_tokens import sign_policy_session_id


class _Repository:
    def __init__(self) -> None:
        self.session: NewPortfolioSession | None = None
        self.documents: dict[str, StoredPolicyDocument] = {}
        self.cache: CachedPortfolioAnalysis | None = None

    def create(self, session: NewPortfolioSession) -> None:
        self.session = session

    def add_document(
        self,
        session_id: str,
        document: StoredPolicyDocument,
        *,
        now: datetime,
        max_documents: int,
    ) -> AddDocumentResult:
        if self.session is None or self.session.id != session_id:
            return "missing"
        if len(self.documents) >= max_documents:
            return "limit_exceeded"
        self.documents[document.id] = document
        return "stored"

    def snapshot(
        self,
        session_id: str,
        *,
        policy_ids: tuple[str, ...] | None,
        now: datetime,
    ) -> PortfolioSessionSnapshot | None:
        if self.session is None or self.session.id != session_id:
            return None
        documents = list(self.documents.values())
        if policy_ids is not None:
            documents = [document for document in documents if document.id in policy_ids]
        return PortfolioSessionSnapshot(
            session_id=session_id,
            version=len(self.documents),
            policies=tuple(document.policy for document in documents),
            rag_session_ids=tuple(
                document.rag_session_id
                for document in documents
                if document.rag_session_id is not None
            ),
        )

    def extend(
        self,
        session_id: str,
        expires_at: datetime,
        *,
        now: datetime,
    ) -> tuple[str, ...] | None:
        snapshot = self.snapshot(session_id, policy_ids=None, now=now)
        return snapshot.rag_session_ids if snapshot else None

    def delete(self, session_id: str) -> tuple[str, ...] | None:
        snapshot = self.snapshot(session_id, policy_ids=None, now=datetime.now(UTC))
        if snapshot is None:
            return None
        self.session = None
        self.documents.clear()
        return snapshot.rag_session_ids

    def load_cached_analysis(
        self,
        session_id: str,
        *,
        version: int,
        context_hash: str,
    ) -> CachedPortfolioAnalysis | None:
        if self.cache is None:
            return None
        if self.cache.version != version or self.cache.context_hash != context_hash:
            return None
        return self.cache

    def save_cached_analysis(
        self,
        session_id: str,
        analysis: CachedPortfolioAnalysis,
    ) -> None:
        self.cache = analysis


class _RagStore:
    def __init__(self) -> None:
        self.extended: list[str] = []
        self.deleted: list[str] = []
        self.expired_cleanup_calls = 0

    def add(self, records: Sequence[PolicyVectorRecord]) -> None:
        raise AssertionError("not used")

    def query(
        self,
        session_ids: Sequence[str],
        query_embedding: tuple[float, ...],
        *,
        top_k: int,
    ) -> list[PolicyRetrievalHit]:
        raise AssertionError("not used")

    def extend(self, session_id: str, expires_at: datetime) -> bool:
        self.extended.append(session_id)
        return True

    def delete(self, session_id: str) -> None:
        self.deleted.append(session_id)

    def delete_expired(self, now: datetime) -> int:
        self.expired_cleanup_calls += 1
        return 0


@pytest.fixture(autouse=True)
def _settings(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.modules.portfolio.session import service
    from app.rag.policy import session_tokens

    class _Settings:
        policy_rag_ttl_seconds = 900
        policy_rag_max_ttl_seconds = 7200
        policy_rag_session_secret = "test-portfolio-session-secret-32-bytes"
        database_url = "postgresql://example/test"
        portfolio_session_max_documents = 50

    monkeypatch.setattr(service, "get_settings", lambda: _Settings())
    monkeypatch.setattr(session_tokens, "get_settings", lambda: _Settings())


def test_session_stores_only_qa_safe_policy_facts_and_selects_documents() -> None:
    now = datetime(2026, 7, 18, tzinfo=UTC)
    repository = _Repository()
    rag_store = _RagStore()
    sessions = PortfolioSessionService(repository, rag_store=rag_store)
    access = sessions.create(now=now)
    rag_token = sign_policy_session_id(
        "rag-document-1",
        datetime(2026, 7, 18, 1, tzinfo=UTC),
    )
    result: PipelineResult = {
        "기본정보": {
            "보험사": "보험사A",
            "상품명": "건강보험",
            "증권번호": "SECRET-CONTRACT-NUMBER",
            "계약자": "홍길동",
            "피보험자": "홍길동",
            "피보험자정보": {"나이": 31, "성별": "남성", "생애단계": "성인"},
        },
        "보장목록": [
            {
                "담보명": "암진단비",
                "가입금액": "3,000만원",
                "보장내용": "암으로 진단 확정된 경우 010-1234-5678",
                "해설": None,
            }
        ],
        "분석상태": "완료",
        "문자수": 100,
        "문서세션ID": rag_token,
    }

    registered = sessions.add_pipeline_result(access.token, result, now=now)
    snapshot = sessions.snapshot(
        access.token,
        policy_ids=[registered.id],
        now=now,
    )

    assert len(snapshot.policies) == 1
    stored = snapshot.policies[0].model_dump(mode="json")
    assert stored["기본정보"]["보험사"] == "보험사A"
    assert stored["보장목록"][0]["보장내용"] == "암으로 진단 확정된 경우 [전화번호]"
    assert "증권번호" not in stored["기본정보"]
    assert "계약자" not in stored["기본정보"]
    assert "피보험자" not in stored["기본정보"]
    assert snapshot.rag_session_ids == ("rag-document-1",)


def test_refresh_and_delete_apply_to_every_linked_rag_document() -> None:
    now = datetime(2026, 7, 18, tzinfo=UTC)
    repository = _Repository()
    rag_store = _RagStore()
    sessions = PortfolioSessionService(repository, rag_store=rag_store)
    access = sessions.create(now=now)
    repository.documents["document-1"] = StoredPolicyDocument(
        id="document-1",
        policy=_empty_policy("document-1"),
        rag_session_id="rag-1",
    )
    repository.documents["document-2"] = StoredPolicyDocument(
        id="document-2",
        policy=_empty_policy("document-2"),
        rag_session_id="rag-2",
    )

    refreshed = sessions.refresh(access.token, now=now)
    sessions.delete(refreshed.token, now=now)

    assert rag_store.extended == ["rag-1", "rag-2"]
    assert rag_store.deleted == ["rag-1", "rag-2"]


def test_document_limit_removes_the_unlinked_rag_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.portfolio.session import service

    class _Settings:
        policy_rag_ttl_seconds = 900
        policy_rag_max_ttl_seconds = 7200
        policy_rag_session_secret = "test-portfolio-session-secret-32-bytes"
        database_url = "postgresql://example/test"
        portfolio_session_max_documents = 1

    monkeypatch.setattr(service, "get_settings", lambda: _Settings())
    now = datetime(2026, 7, 18, tzinfo=UTC)
    repository = _Repository()
    rag_store = _RagStore()
    sessions = PortfolioSessionService(repository, rag_store=rag_store)
    access = sessions.create(now=now)
    first = _empty_pipeline_result()
    sessions.add_pipeline_result(access.token, first, now=now)
    second_rag_token = sign_policy_session_id(
        "rag-over-limit",
        datetime(2026, 7, 18, 1, tzinfo=UTC),
    )
    second = _empty_pipeline_result()
    second["문서세션ID"] = second_rag_token

    with pytest.raises(PortfolioSessionDocumentLimitExceeded):
        sessions.add_pipeline_result(access.token, second, now=now)

    assert len(repository.documents) == 1
    assert rag_store.deleted == ["rag-over-limit"]
    assert rag_store.expired_cleanup_calls == 1


def _empty_policy(document_id: str) -> PolicyInput:
    return PolicyInput.model_validate({"id": document_id, "기본정보": {}, "보장목록": []})


def _empty_pipeline_result() -> PipelineResult:
    return {
        "기본정보": {"보험사": "보험사A"},
        "보장목록": [],
        "분석상태": "완료",
        "문자수": 1,
    }
