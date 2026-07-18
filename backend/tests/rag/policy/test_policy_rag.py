import json
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from app.modules.policy.models import ParsedDocument
from app.rag.embeddings import HashingEmbedder
from app.rag.policy.indexing import build_policy_vector_records, index_policy_document
from app.rag.policy.models import PolicyChunk, PolicyRetrievalHit, PolicyVectorRecord
from app.rag.policy.pii import mask_policy_pii
from app.rag.policy.retrieval import retrieve_policy_context
from app.rag.policy.session_tokens import (
    InvalidPolicySessionToken,
    sign_policy_session_id,
    verify_policy_session_claims,
    verify_policy_session_token,
)
from app.rag.policy.source import build_policy_source_chunks
from evals.rag.policy.retrieval import (
    EVAL_FIXTURE,
    _text_matches_expected_group,
    evaluate_policy_retrieval,
)

RAG_TEST_BIRTH = "90" + "0101"
RAG_TEST_SUFFIX = "123" + "4567"


class _MemoryStore:
    def __init__(self, records: Sequence[PolicyVectorRecord]) -> None:
        self.records = list(records)
        self.queries: list[tuple[str, ...]] = []

    def add(self, records: Sequence[PolicyVectorRecord]) -> None:
        self.records.extend(records)

    def query(
        self,
        session_ids: Sequence[str],
        query_embedding: tuple[float, ...],
        *,
        top_k: int,
    ) -> list[PolicyRetrievalHit]:
        self.queries.append(tuple(session_ids))
        allowed = set(session_ids)
        ranked = sorted(
            (record for record in self.records if record.chunk.session_id in allowed),
            key=lambda record: (
                -sum(
                    left * right
                    for left, right in zip(query_embedding, record.embedding, strict=True)
                ),
                record.chunk.id,
            ),
        )
        return [PolicyRetrievalHit(chunk=record.chunk, score=1.0) for record in ranked[:top_k]]

    def delete(self, session_id: str) -> None:
        self.records = [record for record in self.records if record.chunk.session_id != session_id]

    def delete_expired(self, now: datetime) -> int:
        original_count = len(self.records)
        self.records = [record for record in self.records if record.chunk.expires_at > now]
        return original_count - len(self.records)

    def extend(self, session_id: str, expires_at: datetime) -> bool:
        updated = False
        records: list[PolicyVectorRecord] = []
        for record in self.records:
            if record.chunk.session_id != session_id:
                records.append(record)
                continue
            updated = True
            records.append(
                PolicyVectorRecord(
                    chunk=replace(record.chunk, expires_at=expires_at),
                    embedding=record.embedding,
                )
            )
        self.records = records
        return updated


class _FailingEmbedder:
    def embed_texts(self, texts: list[str]) -> list[tuple[float, ...]]:
        raise AssertionError("embedder should not be called")


class _FixedEmbedder:
    def embed_texts(self, texts: list[str]) -> list[tuple[float, ...]]:
        return [(1.0,) for _ in texts]


@pytest.fixture(autouse=True)
def _policy_session_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.rag.policy import session_tokens

    class _Settings:
        policy_rag_session_secret = "test-policy-rag-session-secret-32"
        database_url = "postgresql://example/test"

    monkeypatch.setattr(session_tokens, "get_settings", lambda: _Settings())


def _document() -> ParsedDocument:
    return ParsedDocument(
        text="연락처 010-0000-0000\n보험기간은 2036년까지입니다.",
        layout_text="",
        tables=((("담보명", "가입금액"), ("암진단비", "3천만원")),),
    )


def test_policy_source_keeps_text_and_table_structure() -> None:
    chunks = build_policy_source_chunks(_document())

    assert {chunk.content_type for chunk in chunks} == {"text", "table"}
    table = next(chunk for chunk in chunks if chunk.content_type == "table")
    assert "| 담보명 | 가입금액 |" in table.text
    assert "| 암진단비 | 3천만원 |" in table.text


def test_policy_records_mask_pii_before_embedding_and_storage() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    records = build_policy_vector_records(
        _document(),
        session_id="session-1",
        created_at=now,
        expires_at=now + timedelta(hours=1),
        embedder=HashingEmbedder(),
    )

    rendered = "\n".join(record.chunk.text for record in records)
    assert "010-0000-0000" not in rendered
    assert "[전화번호]" in rendered
    assert mask_policy_pii(f"{RAG_TEST_BIRTH}-{RAG_TEST_SUFFIX}") == "[주민등록번호]"


def test_policy_pii_masks_landline_and_representative_phone_numbers() -> None:
    text = "지역번호 " + "02-" + "2345" + "-" + "6789"
    text += "\n대표번호 " + "1688-" + "1234"

    masked = mask_policy_pii(text)

    assert "02-" not in masked
    assert "1688-" not in masked
    assert masked.count("[전화번호]") == 2


def test_policy_pii_masks_contact_and_policy_identifiers() -> None:
    text = (
        "이메일 test.person@example.com\n"
        "주소: 서울시 중구 세종대로 1\n"
        "계좌번호 123-456-789012\n"
        "증권번호: POLICY-SECRET-001\n"
        "차량번호 12가3456\n"
        "계약자 테스트고객"
    )

    masked = mask_policy_pii(text, sensitive_values=("테스트고객",))

    for value in (
        "test.person@example.com",
        "서울시 중구 세종대로 1",
        "123-456-789012",
        "POLICY-SECRET-001",
        "12가3456",
        "테스트고객",
    ):
        assert value not in masked
    assert "[이메일]" in masked
    assert "[주소]" in masked
    assert "[계좌번호]" in masked


def test_policy_pii_keeps_large_amounts() -> None:
    text = "가입금액은 30,000,000원이고 보상한도는 100,000,000원입니다."
    text += "\n정액 보장금액은 10000000원입니다."

    assert mask_policy_pii(text) == text


def test_policy_index_returns_signed_session_token() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    store = _MemoryStore(())
    token = index_policy_document(
        _document(),
        store=store,
        embedder=HashingEmbedder(),
        now=now,
    )

    assert token is not None
    claims = verify_policy_session_claims(token, now=now)
    assert len(claims.session_id) == 32
    assert claims.expires_at == now + timedelta(minutes=15)
    assert claims.max_expires_at == now + timedelta(hours=2)
    assert {record.chunk.session_id for record in store.records} == {claims.session_id}


def test_policy_retrieval_reranks_lexical_match_within_vector_candidates() -> None:
    now = datetime.now(UTC)
    expires_at = now + timedelta(hours=1)
    records = (
        PolicyVectorRecord(
            chunk=PolicyChunk(
                id="session-1:1",
                session_id="session-1",
                text="보험료 납입 안내와 일반 유의사항입니다.",
                content_type="text",
                chunk_index=1,
                table_index=None,
                created_at=now,
                expires_at=expires_at,
            ),
            embedding=(1.0,),
        ),
        PolicyVectorRecord(
            chunk=PolicyChunk(
                id="session-1:2",
                session_id="session-1",
                text="암진단비 유사암제외 가입금액은 4,000만원입니다.",
                content_type="text",
                chunk_index=2,
                table_index=None,
                created_at=now,
                expires_at=expires_at,
            ),
            embedding=(0.5,),
        ),
    )
    token = sign_policy_session_id("session-1", expires_at)

    hits = retrieve_policy_context(
        [token],
        "암진단비 유사암제외 가입금액",
        top_k=1,
        candidate_k=2,
        store=_MemoryStore(records),
        embedder=_FixedEmbedder(),
    )

    assert hits[0].chunk.id == "session-1:2"


def test_policy_session_token_rejects_forgery_and_expiry() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    token = sign_policy_session_id(
        "session-1",
        now + timedelta(hours=1),
        max_expires_at=now + timedelta(hours=2),
        secret="test-secret",
    )

    assert verify_policy_session_token(token, secret="test-secret", now=now) == "session-1"

    forged = token.replace("session-1", "session-2")
    with pytest.raises(InvalidPolicySessionToken):
        verify_policy_session_token(forged, secret="test-secret", now=now)

    with pytest.raises(InvalidPolicySessionToken):
        verify_policy_session_token(
            token,
            secret="test-secret",
            now=now + timedelta(hours=3),
        )


def test_policy_session_token_requires_configured_secret_when_database_is_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.rag.policy import session_tokens

    class _Settings:
        policy_rag_session_secret = ""
        database_url = "postgresql://example/test"

    monkeypatch.setattr(session_tokens, "get_settings", lambda: _Settings())

    with pytest.raises(RuntimeError, match="POLICY_RAG_SESSION_SECRET"):
        sign_policy_session_id("session-1", datetime(2030, 1, 1, tzinfo=UTC))


def test_policy_session_token_rejects_placeholder_configured_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.rag.policy import session_tokens

    class _Settings:
        policy_rag_session_secret = "replace-with-random-secret"
        database_url = "postgresql://example/test"

    monkeypatch.setattr(session_tokens, "get_settings", lambda: _Settings())

    with pytest.raises(RuntimeError, match="random secret"):
        sign_policy_session_id("session-1", datetime(2030, 1, 1, tzinfo=UTC))


def test_policy_session_token_rejects_weak_configured_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.rag.policy import session_tokens

    class _Settings:
        policy_rag_session_secret = "short-secret"
        database_url = "postgresql://example/test"

    monkeypatch.setattr(session_tokens, "get_settings", lambda: _Settings())

    with pytest.raises(RuntimeError, match="at least 32 bytes"):
        sign_policy_session_id("session-1", datetime(2030, 1, 1, tzinfo=UTC))


def test_policy_index_validates_secret_before_embedding_or_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.rag.policy import session_tokens

    class _Settings:
        policy_rag_session_secret = ""
        database_url = "postgresql://example/test"

    store = _MemoryStore(())
    monkeypatch.setattr(session_tokens, "get_settings", lambda: _Settings())

    with pytest.raises(RuntimeError, match="POLICY_RAG_SESSION_SECRET"):
        index_policy_document(
            _document(),
            store=store,
            embedder=_FailingEmbedder(),
            now=datetime(2026, 1, 1, tzinfo=UTC),
        )

    assert store.records == []


def test_policy_retrieval_is_limited_to_requested_sessions() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    embedder = HashingEmbedder()
    first = build_policy_vector_records(
        _document(),
        session_id="session-1",
        created_at=now,
        expires_at=now + timedelta(hours=1),
        embedder=embedder,
    )
    other = build_policy_vector_records(
        ParsedDocument(text="다른 사용자 비밀 담보", layout_text="", tables=()),
        session_id="session-2",
        created_at=now,
        expires_at=now + timedelta(hours=1),
        embedder=embedder,
    )

    token = sign_policy_session_id("session-1", datetime(2030, 1, 1, tzinfo=UTC))
    store = _MemoryStore((*first, *other))
    hits = retrieve_policy_context(
        [token],
        "암진단비 가입금액",
        store=store,
        embedder=embedder,
    )

    assert hits
    assert {hit.chunk.session_id for hit in hits} == {"session-1"}
    assert store.queries == [("session-1",)]


def test_policy_retrieval_rejects_raw_or_forged_session_ids() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    embedder = HashingEmbedder()
    records = build_policy_vector_records(
        _document(),
        session_id="session-1",
        created_at=now,
        expires_at=now + timedelta(hours=1),
        embedder=embedder,
    )
    store = _MemoryStore(records)

    assert (
        retrieve_policy_context(
            ["session-1"],
            "암진단비 가입금액",
            store=store,
            embedder=embedder,
        )
        == []
    )
    assert store.queries == []


def test_policy_retrieval_keeps_valid_sessions_when_one_token_is_invalid() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    embedder = HashingEmbedder()
    first = build_policy_vector_records(
        _document(),
        session_id="session-1",
        created_at=now,
        expires_at=now + timedelta(hours=1),
        embedder=embedder,
    )
    second = build_policy_vector_records(
        ParsedDocument(text="다른 증권 담보", layout_text="", tables=()),
        session_id="session-2",
        created_at=now,
        expires_at=now + timedelta(hours=1),
        embedder=embedder,
    )

    token = sign_policy_session_id("session-1", datetime(2030, 1, 1, tzinfo=UTC))
    store = _MemoryStore((*first, *second))
    hits = retrieve_policy_context(
        [token, "not-a-server-issued-token"],
        "암진단비 가입금액",
        store=store,
        embedder=embedder,
    )

    assert hits
    assert {hit.chunk.session_id for hit in hits} == {"session-1"}
    assert store.queries == [("session-1",)]


def test_policy_retrieval_dedupes_identical_chunks() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    embedder = HashingEmbedder()
    duplicate_doc = ParsedDocument(
        text="중복 문구",
        layout_text="",
        tables=(
            (("항목", "값"), ("상품명", "테스트보험")),
            (("항목", "값"), ("상품명", "테스트보험")),
        ),
    )
    records = build_policy_vector_records(
        duplicate_doc,
        session_id="session-1",
        created_at=now,
        expires_at=now + timedelta(hours=1),
        embedder=embedder,
    )
    token = sign_policy_session_id("session-1", datetime(2030, 1, 1, tzinfo=UTC))

    hits = retrieve_policy_context(
        [token],
        "상품명은?",
        store=_MemoryStore(records),
        embedder=embedder,
        top_k=4,
        candidate_k=8,
    )

    rendered = [hit.chunk.text for hit in hits]
    assert len(rendered) == len(set(rendered))


def test_policy_retrieval_normalizes_query_whitespace_only() -> None:
    class _CapturingEmbedder:
        def __init__(self) -> None:
            self.calls: list[list[str]] = []

        def embed_texts(self, texts: list[str]) -> list[tuple[float, ...]]:
            self.calls.append(texts)
            return [(1.0, 0.0) for _ in texts]

    embedder = _CapturingEmbedder()
    token = sign_policy_session_id("session-1", datetime(2030, 1, 1, tzinfo=UTC))
    retrieve_policy_context(
        [token],
        "  보험기간은   언제까지야?  ",
        store=_MemoryStore(()),
        embedder=embedder,
    )

    assert embedder.calls == [["보험기간은 언제까지야?"]]


def test_policy_retrieval_evaluation_passes_fixture() -> None:
    documents = {
        "policy-a.pdf": ParsedDocument(
            text="보험기간은 2036년까지입니다.",
            layout_text="",
            tables=((("담보명", "가입금액"), ("암진단비", "3천만원")),),
        ),
        "policy-b.pdf": ParsedDocument(
            text="월 보험료는 87,000원입니다.",
            layout_text="",
            tables=(),
        ),
    }
    raw = {
        "source": "sample-insurance-input",
        "documents": [
            {"session_id": "session-a", "filename": "policy-a.pdf"},
            {"session_id": "session-b", "filename": "policy-b.pdf"},
        ],
        "cases": [
            {
                "id": "coverage",
                "query": "암진단비 가입금액은 얼마야?",
                "session_ids": ["session-a"],
                "expected_session_id": "session-a",
                "expected_term_groups": [["암진단비", "3천만원"]],
            },
            {
                "id": "premium",
                "query": "월 보험료는 얼마야?",
                "session_ids": ["session-b"],
                "expected_session_id": "session-b",
                "expected_term_groups": [["월 보험료", "87,000원"]],
            },
        ],
    }

    with TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        sample_dir = root / "sample-insurance-input"
        sample_dir.mkdir()
        for filename in documents:
            (sample_dir / filename).write_bytes(b"fake-pdf")
        dataset = root / "evaluation_dataset.json"
        dataset.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

        calls = iter(documents.values())

        def parse_in_order(_: bytes) -> ParsedDocument:
            return next(calls)

        report = evaluate_policy_retrieval(
            path=dataset,
            sample_dir=sample_dir,
            parse=parse_in_order,
        )

    assert report.recall == 1.0
    assert report.mrr > 0.0


def test_policy_retrieval_evaluation_can_use_production_embedder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    documents = {
        "policy-a.pdf": ParsedDocument(
            text="월 보험료는 87,000원입니다.",
            layout_text="",
            tables=(),
        ),
    }
    raw = {
        "source": "sample-insurance-input",
        "documents": [{"session_id": "session-a", "filename": "policy-a.pdf"}],
        "cases": [
            {
                "id": "premium",
                "query": "월 보험료는 얼마야?",
                "session_ids": ["session-a"],
                "expected_session_id": "session-a",
                "expected_term_groups": [["월 보험료", "87,000원"]],
            },
        ],
    }
    calls: list[list[str]] = []

    class _StubProductionEmbedder:
        def embed_texts(self, texts: list[str]) -> list[tuple[float, ...]]:
            calls.append(texts)
            return [(1.0, 0.0) for _ in texts]

    monkeypatch.setattr(
        "evals.rag.policy.retrieval.openai_embedder_from_settings",
        lambda: _StubProductionEmbedder(),
    )

    with TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        sample_dir = root / "sample-insurance-input"
        sample_dir.mkdir()
        (sample_dir / "policy-a.pdf").write_bytes(b"fake-pdf")
        dataset = root / "evaluation_dataset.json"
        dataset.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

        store = _MemoryStore(())
        report = evaluate_policy_retrieval(
            path=dataset,
            sample_dir=sample_dir,
            production=True,
            store=store,
            parse=lambda _: next(iter(documents.values())),
        )

    assert report.recall == 1.0
    assert calls
    assert store.records == []


def test_local_policy_eval_dataset_has_product_scale_cases() -> None:
    raw = json.loads(EVAL_FIXTURE.read_text(encoding="utf-8"))
    cases = raw["cases"]
    case_ids = [case["id"] for case in cases]

    assert len(cases) >= 120
    assert len(case_ids) == len(set(case_ids))
    assert sum(case_id.startswith("paraphrase-") for case_id in case_ids) >= 12
    assert sum(case_id.startswith("noisy-") for case_id in case_ids) >= 8
    assert sum(len(case["session_ids"]) > 1 for case in cases) >= 14


def test_local_policy_eval_dataset_does_not_contain_sample_pii() -> None:
    rendered = EVAL_FIXTURE.read_text(encoding="utf-8")
    blocked_terms = (
        "테스트고객A",
        "95" + "0524",
        "POLICY-TEST-MASKED-001",
        "POLICY-TEST-LOCAL-002",
        "POLICY-TEST-MASKED-003",
        "POLICY-TEST-LOCAL-004",
        "TEST-PLATE-002",
        "1688-1688",
    )

    assert not any(term in rendered for term in blocked_terms)


def test_policy_eval_normalizes_expected_term_matching() -> None:
    documents = {
        "policy-a.pdf": ParsedDocument(
            text="보험기간은 2020-05-06~2095-05-06 입니다.",
            layout_text="",
            tables=(),
        ),
    }
    raw = {
        "source": "sample-insurance-input",
        "documents": [{"session_id": "session-a", "filename": "policy-a.pdf"}],
        "cases": [
            {
                "id": "period",
                "query": "보험기간은?",
                "session_ids": ["session-a"],
                "expected_session_id": "session-a",
                "expected_terms": ["2020-05-06 ~ 2095-05-06"],
            },
        ],
    }

    with TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        sample_dir = root / "sample-insurance-input"
        sample_dir.mkdir()
        (sample_dir / "policy-a.pdf").write_bytes(b"fake-pdf")
        dataset = root / "evaluation_dataset.json"
        dataset.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

        report = evaluate_policy_retrieval(
            path=dataset,
            sample_dir=sample_dir,
            parse=lambda _: next(iter(documents.values())),
        )

    assert report.recall == 1.0


def test_policy_eval_accepts_masked_or_plain_phone_numbers() -> None:
    documents = {
        "policy-a.pdf": ParsedDocument(
            text="권유자 연락처는 000-0000-0000 입니다.",
            layout_text="",
            tables=(),
        ),
    }
    raw = {
        "source": "sample-insurance-input",
        "documents": [{"session_id": "session-a", "filename": "policy-a.pdf"}],
        "cases": [
            {
                "id": "phone",
                "query": "연락처는?",
                "session_ids": ["session-a"],
                "expected_session_id": "session-a",
                "expected_term_groups": [["권유자 연락처", "[전화번호]"]],
            },
        ],
    }

    with TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        sample_dir = root / "sample-insurance-input"
        sample_dir.mkdir()
        (sample_dir / "policy-a.pdf").write_bytes(b"fake-pdf")
        dataset = root / "evaluation_dataset.json"
        dataset.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

        report = evaluate_policy_retrieval(
            path=dataset,
            sample_dir=sample_dir,
            parse=lambda _: next(iter(documents.values())),
        )

    assert report.recall == 1.0


def test_policy_eval_accepts_any_expected_term_variant() -> None:
    documents = {
        "policy-a.pdf": ParsedDocument(
            text="계약사항 20년만기 / 20년납 / 월납",
            layout_text="",
            tables=(),
        ),
    }
    raw = {
        "source": "sample-insurance-input",
        "documents": [{"session_id": "session-a", "filename": "policy-a.pdf"}],
        "cases": [
            {
                "id": "payment-term",
                "query": "납입기간과 납입주기는?",
                "session_ids": ["session-a"],
                "expected_session_id": "session-a",
                "expected_term_groups": [
                    ["납입기간", "20년납", "월납"],
                    ["20년만기 / 20년납 / 월납"],
                ],
            },
        ],
    }

    with TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        sample_dir = root / "sample-insurance-input"
        sample_dir.mkdir()
        (sample_dir / "policy-a.pdf").write_bytes(b"fake-pdf")
        dataset = root / "evaluation_dataset.json"
        dataset.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

        report = evaluate_policy_retrieval(
            path=dataset,
            sample_dir=sample_dir,
            parse=lambda _: next(iter(documents.values())),
        )

    assert report.recall == 1.0


def test_policy_eval_requires_all_terms_in_expected_group() -> None:
    assert _text_matches_expected_group(
        "암진단비 가입금액은 3천만원입니다.",
        (("암진단비", "3천만원"),),
    )
    assert not _text_matches_expected_group(
        "상해사망 가입금액은 3천만원입니다.",
        (("암진단비", "3천만원"),),
    )


def test_policy_eval_session_precision_uses_all_requested_sessions() -> None:
    documents = {
        "policy-a.pdf": ParsedDocument(
            text="월 보험료는 87,000원입니다.",
            layout_text="",
            tables=(),
        ),
        "policy-b.pdf": ParsedDocument(
            text="월 보험료는 42,000원입니다.",
            layout_text="",
            tables=(),
        ),
    }
    raw = {
        "source": "sample-insurance-input",
        "documents": [
            {"session_id": "session-a", "filename": "policy-a.pdf"},
            {"session_id": "session-b", "filename": "policy-b.pdf"},
        ],
        "cases": [
            {
                "id": "premium",
                "query": "월 보험료는 얼마야?",
                "session_ids": ["session-a", "session-b"],
                "expected_session_id": "session-a",
                "expected_term_groups": [["87,000원"]],
            },
        ],
    }

    with TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        sample_dir = root / "sample-insurance-input"
        sample_dir.mkdir()
        for filename in documents:
            (sample_dir / filename).write_bytes(b"fake-pdf")
        dataset = root / "evaluation_dataset.json"
        dataset.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

        calls = iter(documents.values())
        report = evaluate_policy_retrieval(
            path=dataset,
            sample_dir=sample_dir,
            parse=lambda _: next(calls),
            top_k=2,
        )

    assert report.session_precision < 1.0
