from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import SecretStr

from app.modules.policy.pipeline import PipelineResult
from app.modules.portfolio.schemas import PolicyInput
from app.modules.portfolio.session.models import (
    CachedPortfolioAnalysis,
    NewPortfolioSession,
    PolicyDocumentReservation,
    PortfolioSessionSnapshot,
    StoredPolicyDocument,
)
from app.modules.portfolio.session.repository import (
    CompleteDocumentResult,
    ReserveDocumentResult,
)
from app.modules.portfolio.session.service import (
    CounselTurnLimitReached,
    InvalidPortfolioSessionToken,
    PortfolioSessionDocumentAlreadyCompleted,
    PortfolioSessionDocumentCancelled,
    PortfolioSessionDocumentInProgress,
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
        self.version = 0
        self.cancelled_document_ids: set[str] = set()
        self.reservations: dict[str, tuple[str, datetime]] = {}
        self.counsel_turns_used = 0

    def counsel_turns_remaining(
        self,
        session_id: str,
        *,
        now: datetime,
        max_turns: int,
    ) -> int | None:
        if self.session is None or self.session.id != session_id:
            return None
        return max(0, max_turns - self.counsel_turns_used)

    def consume_counsel_turn(
        self,
        session_id: str,
        *,
        now: datetime,
        max_turns: int,
    ) -> int | None:
        if self.session is None or self.session.id != session_id:
            return None
        if self.counsel_turns_used >= max_turns:
            return None
        self.counsel_turns_used += 1
        return max_turns - self.counsel_turns_used

    def refund_counsel_turn(self, session_id: str, *, now: datetime) -> bool:
        if self.session is None or self.session.id != session_id:
            return False
        if self.counsel_turns_used <= 0:
            return False
        self.counsel_turns_used -= 1
        return True

    def create(self, session: NewPortfolioSession) -> None:
        self.session = session

    def reserve_document(
        self,
        session_id: str,
        document_id: str,
        reservation_id: str,
        *,
        now: datetime,
        expires_at: datetime,
        max_documents: int,
    ) -> ReserveDocumentResult:
        if self.session is None or self.session.id != session_id:
            return "missing"
        if document_id in self.cancelled_document_ids:
            return "cancelled"
        self.reservations = {
            reserved_id: reservation
            for reserved_id, reservation in self.reservations.items()
            if reservation[1] > now
        }
        if document_id in self.reservations:
            return "in_progress"
        if document_id in self.documents:
            return "completed"
        if len(self.documents) + len(self.reservations) >= max_documents:
            return "limit_exceeded"
        self.reservations[document_id] = (reservation_id, expires_at)
        return "reserved"

    def complete_document(
        self,
        reservation: PolicyDocumentReservation,
        document: StoredPolicyDocument,
        *,
        now: datetime,
    ) -> CompleteDocumentResult:
        if self.session is None or self.session.id != reservation.session_id:
            return "missing"
        if reservation.document_id in self.cancelled_document_ids:
            self.reservations.pop(reservation.document_id, None)
            return "cancelled"
        stored_reservation = self.reservations.get(reservation.document_id)
        if stored_reservation is None or stored_reservation[0] != reservation.reservation_id:
            return "missing"
        if stored_reservation[1] <= now:
            return "missing"
        self.reservations.pop(reservation.document_id)
        self.documents[document.id] = document
        self.version += 1
        self.cache = None
        return "stored"

    def release_document(self, reservation: PolicyDocumentReservation) -> None:
        stored_reservation = self.reservations.get(reservation.document_id)
        if stored_reservation is not None and stored_reservation[0] == reservation.reservation_id:
            self.reservations.pop(reservation.document_id)

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
            version=self.version,
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

    def delete_documents(
        self,
        session_id: str,
        document_ids: tuple[str, ...],
        *,
        now: datetime,
    ) -> tuple[str, ...] | None:
        if self.session is None or self.session.id != session_id:
            return None
        self.cancelled_document_ids.update(document_ids)
        for document_id in document_ids:
            self.reservations.pop(document_id, None)
        deleted = [
            self.documents.pop(document_id)
            for document_id in document_ids
            if document_id in self.documents
        ]
        if deleted:
            self.version += 1
            self.cache = None
        return tuple(
            document.rag_session_id for document in deleted if document.rag_session_id is not None
        )

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
        policy_rag_session_secret = SecretStr("test-portfolio-session-secret-32-bytes")
        database_url = SecretStr("postgresql://example/test")
        portfolio_session_max_documents = 50
        policy_upload_reservation_ttl_seconds = 300

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
            "피보험자": "김보험",
            "피보험자정보": {"나이": 31, "성별": "남성", "생애단계": "성인"},
        },
        "보장목록": [
            {
                "담보명": "암진단비",
                "가입금액": "3,000만원",
                "보장내용": "김보험님이 암으로 진단 확정된 경우 010-1234-5678",
                "해설": "계약자 홍길동에게 안내",
            }
        ],
        "분석상태": "완료",
        "policy_terms_status": "available",
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
    assert stored["보장목록"][0]["보장내용"] == (
        "[개인정보]님이 암으로 진단 확정된 경우 [전화번호]"
    )
    assert stored["보장목록"][0]["해설"] == "계약자 [개인정보]에게 안내"
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


def test_delete_documents_invalidates_analysis_and_removes_linked_rag_sessions() -> None:
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
    repository.cache = CachedPortfolioAnalysis(
        version=0,
        context_hash="context",
        result={},
    )

    sessions.delete_documents(
        access.token,
        ["document-1", "document-1", "missing-document"],
        now=now,
    )

    assert set(repository.documents) == {"document-2"}
    assert repository.version == 1
    assert repository.cache is None
    assert rag_store.deleted == ["rag-1"]


def test_cancelled_document_cannot_be_stored_after_delete_wins_the_race() -> None:
    now = datetime(2026, 7, 18, tzinfo=UTC)
    repository = _Repository()
    sessions = PortfolioSessionService(repository, rag_store=_RagStore())
    access = sessions.create(now=now)

    sessions.delete_documents(access.token, ["document-1"], now=now)

    with pytest.raises(PortfolioSessionDocumentCancelled):
        sessions.add_pipeline_result(
            access.token,
            _empty_pipeline_result(),
            document_id="document-1",
            now=now,
        )

    assert repository.documents == {}


def test_cancellation_after_reservation_removes_late_rag_document() -> None:
    now = datetime(2026, 7, 18, tzinfo=UTC)
    repository = _Repository()
    rag_store = _RagStore()
    sessions = PortfolioSessionService(repository, rag_store=rag_store)
    access = sessions.create(now=now)
    reservation = sessions.begin_upload(
        access.token,
        document_id="document-1",
        now=now,
    )
    rag_token = sign_policy_session_id(
        "late-rag-document",
        datetime(2026, 7, 18, 1, tzinfo=UTC),
    )
    result = _empty_pipeline_result()
    result["문서세션ID"] = rag_token

    sessions.delete_documents(access.token, ["document-1"], now=now)

    with pytest.raises(PortfolioSessionDocumentCancelled):
        sessions.complete_upload(reservation, result, now=now)

    assert repository.documents == {}
    assert repository.reservations == {}
    assert rag_store.deleted == ["late-rag-document"]


def test_failed_completion_releases_slot_and_removes_rag_document() -> None:
    class _FailingRepository(_Repository):
        def complete_document(
            self,
            reservation: PolicyDocumentReservation,
            document: StoredPolicyDocument,
            *,
            now: datetime,
        ) -> CompleteDocumentResult:
            raise RuntimeError("database unavailable")

    now = datetime(2026, 7, 18, tzinfo=UTC)
    repository = _FailingRepository()
    rag_store = _RagStore()
    sessions = PortfolioSessionService(repository, rag_store=rag_store)
    access = sessions.create(now=now)
    reservation = sessions.begin_upload(
        access.token,
        document_id="document-1",
        now=now,
    )
    rag_token = sign_policy_session_id(
        "failed-rag-document",
        datetime(2026, 7, 18, 1, tzinfo=UTC),
    )
    result = _empty_pipeline_result()
    result["문서세션ID"] = rag_token

    with pytest.raises(RuntimeError, match="database unavailable"):
        sessions.complete_upload(reservation, result, now=now)

    assert repository.reservations == {}
    assert rag_store.deleted == ["failed-rag-document"]


def test_document_limit_removes_the_unlinked_rag_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.portfolio.session import service

    class _Settings:
        policy_rag_ttl_seconds = 900
        policy_rag_max_ttl_seconds = 7200
        policy_rag_session_secret = SecretStr("test-portfolio-session-secret-32-bytes")
        database_url = SecretStr("postgresql://example/test")
        portfolio_session_max_documents = 1
        policy_upload_reservation_ttl_seconds = 300

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


def test_in_progress_upload_counts_toward_document_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.portfolio.session import service

    class _Settings:
        policy_rag_ttl_seconds = 900
        policy_rag_max_ttl_seconds = 7200
        policy_rag_session_secret = SecretStr("test-portfolio-session-secret-32-bytes")
        database_url = SecretStr("postgresql://example/test")
        portfolio_session_max_documents = 1
        policy_upload_reservation_ttl_seconds = 300

    monkeypatch.setattr(service, "get_settings", lambda: _Settings())
    now = datetime(2026, 7, 18, tzinfo=UTC)
    repository = _Repository()
    sessions = PortfolioSessionService(repository, rag_store=_RagStore())
    access = sessions.create(now=now)
    first = sessions.begin_upload(access.token, document_id="document-1", now=now)

    with pytest.raises(PortfolioSessionDocumentLimitExceeded):
        sessions.begin_upload(access.token, document_id="document-2", now=now)

    sessions.release_upload(first)
    second = sessions.begin_upload(access.token, document_id="document-2", now=now)

    assert second.document_id == "document-2"


def test_duplicate_document_id_does_not_share_or_release_an_active_reservation() -> None:
    now = datetime(2026, 7, 18, tzinfo=UTC)
    repository = _Repository()
    sessions = PortfolioSessionService(repository, rag_store=_RagStore())
    access = sessions.create(now=now)

    first = sessions.begin_upload(access.token, document_id="document-1", now=now)

    with pytest.raises(PortfolioSessionDocumentInProgress):
        sessions.begin_upload(access.token, document_id="document-1", now=now)

    assert "document-1" in repository.reservations
    sessions.release_upload(first)
    assert repository.reservations == {}


def test_completed_document_id_is_distinct_from_an_active_upload() -> None:
    now = datetime(2026, 7, 18, tzinfo=UTC)
    repository = _Repository()
    sessions = PortfolioSessionService(repository, rag_store=_RagStore())
    access = sessions.create(now=now)

    reservation = sessions.begin_upload(
        access.token,
        document_id="document-1",
        now=now,
    )
    sessions.complete_upload(reservation, _empty_pipeline_result(), now=now)

    with pytest.raises(PortfolioSessionDocumentAlreadyCompleted):
        sessions.begin_upload(access.token, document_id="document-1", now=now)


def test_expired_upload_reservation_releases_its_document_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.portfolio.session import service

    class _Settings:
        policy_rag_ttl_seconds = 900
        policy_rag_max_ttl_seconds = 7200
        policy_rag_session_secret = SecretStr("test-portfolio-session-secret-32-bytes")
        database_url = SecretStr("postgresql://example/test")
        portfolio_session_max_documents = 1
        policy_upload_reservation_ttl_seconds = 30

    monkeypatch.setattr(service, "get_settings", lambda: _Settings())
    now = datetime(2026, 7, 18, tzinfo=UTC)
    repository = _Repository()
    sessions = PortfolioSessionService(repository, rag_store=_RagStore())
    access = sessions.create(now=now)
    sessions.begin_upload(access.token, document_id="document-1", now=now)

    next_reservation = sessions.begin_upload(
        access.token,
        document_id="document-2",
        now=now + timedelta(seconds=31),
    )

    assert next_reservation.document_id == "document-2"
    assert set(repository.reservations) == {"document-2"}


def test_stale_reservation_cannot_release_or_complete_a_new_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.portfolio.session import service

    class _Settings:
        policy_rag_ttl_seconds = 900
        policy_rag_max_ttl_seconds = 7200
        policy_rag_session_secret = SecretStr("test-portfolio-session-secret-32-bytes")
        database_url = SecretStr("postgresql://example/test")
        portfolio_session_max_documents = 1
        policy_upload_reservation_ttl_seconds = 30

    monkeypatch.setattr(service, "get_settings", lambda: _Settings())
    now = datetime(2026, 7, 18, tzinfo=UTC)
    later = now + timedelta(seconds=31)
    repository = _Repository()
    sessions = PortfolioSessionService(repository, rag_store=_RagStore())
    access = sessions.create(now=now)
    stale = sessions.begin_upload(access.token, document_id="document-1", now=now)
    current = sessions.begin_upload(access.token, document_id="document-1", now=later)

    sessions.release_upload(stale)
    assert repository.reservations["document-1"][0] == current.reservation_id

    with pytest.raises(InvalidPortfolioSessionToken):
        sessions.complete_upload(stale, _empty_pipeline_result(), now=later)

    assert repository.reservations["document-1"][0] == current.reservation_id
    completed = sessions.complete_upload(current, _empty_pipeline_result(), now=later)
    assert completed.id == "document-1"


def _empty_policy(document_id: str) -> PolicyInput:
    return PolicyInput.model_validate({"id": document_id, "기본정보": {}, "보장목록": []})


def _empty_pipeline_result() -> PipelineResult:
    return {
        "기본정보": {"보험사": "보험사A"},
        "보장목록": [],
        "분석상태": "완료",
        "policy_terms_status": "unavailable",
        "문자수": 1,
    }


def test_counsel_turns_run_out_after_the_configured_limit() -> None:
    now = datetime(2026, 7, 18, tzinfo=UTC)
    repository = _Repository()
    sessions = PortfolioSessionService(repository, rag_store=_RagStore())
    access = sessions.create(now=now)

    remaining = [
        sessions.consume_counsel_turn(access.token, max_turns=3, now=now) for _ in range(3)
    ]

    assert remaining == [2, 1, 0]
    with pytest.raises(CounselTurnLimitReached):
        sessions.consume_counsel_turn(access.token, max_turns=3, now=now)


def test_refunding_a_failed_counsel_turn_restores_the_session_allowance() -> None:
    now = datetime(2026, 7, 18, tzinfo=UTC)
    repository = _Repository()
    sessions = PortfolioSessionService(repository, rag_store=_RagStore())
    access = sessions.create(now=now)

    assert sessions.consume_counsel_turn(access.token, max_turns=2, now=now) == 1

    sessions.refund_counsel_turn(access.token, now=now)

    assert sessions.consume_counsel_turn(access.token, max_turns=2, now=now) == 1


def test_adding_a_policy_document_does_not_restore_counsel_turns() -> None:
    # The cap belongs to the session, not to what is in it. Uploading another
    # policy must not hand the user a fresh allowance.
    now = datetime(2026, 7, 18, tzinfo=UTC)
    repository = _Repository()
    sessions = PortfolioSessionService(repository, rag_store=_RagStore())
    access = sessions.create(now=now)
    sessions.consume_counsel_turn(access.token, max_turns=2, now=now)

    repository.documents["document-1"] = StoredPolicyDocument(
        id="document-1",
        policy=PolicyInput.model_validate({"id": "document-1", "기본정보": {}, "보장목록": []}),
        rag_session_id=None,
    )

    assert sessions.consume_counsel_turn(access.token, max_turns=2, now=now) == 0
    with pytest.raises(CounselTurnLimitReached):
        sessions.consume_counsel_turn(access.token, max_turns=2, now=now)
