import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from app.services.policy.models import ParsedDocument
from app.services.rag.embeddings import HashingEmbedder
from app.services.rag.policy.evaluation import EVAL_FIXTURE, evaluate_policy_retrieval
from app.services.rag.policy.indexing import build_policy_vector_records
from app.services.rag.policy.models import PolicyRetrievalHit, PolicyVectorRecord
from app.services.rag.policy.pii import mask_policy_pii
from app.services.rag.policy.retrieval import retrieve_policy_context
from app.services.rag.policy.source import build_policy_source_chunks


class _MemoryStore:
    def __init__(self, records: Sequence[PolicyVectorRecord]) -> None:
        self.records = list(records)

    def add(self, records: Sequence[PolicyVectorRecord]) -> None:
        self.records.extend(records)

    def query(
        self,
        session_ids: Sequence[str],
        query_embedding: tuple[float, ...],
        *,
        top_k: int,
    ) -> list[PolicyRetrievalHit]:
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
    assert mask_policy_pii("TESTBIRTH-E-TESTSUFFIX") == "[주민등록번호]"


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

    hits = retrieve_policy_context(
        ["session-1"],
        "암진단비 가입금액",
        store=_MemoryStore((*first, *other)),
        embedder=embedder,
    )

    assert hits
    assert {hit.chunk.session_id for hit in hits} == {"session-1"}


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
                "expected_term": "3천만원",
            },
            {
                "id": "premium",
                "query": "월 보험료는 얼마야?",
                "session_ids": ["session-b"],
                "expected_session_id": "session-b",
                "expected_term": "87,000원",
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
                "expected_term": "87,000원",
            },
        ],
    }
    calls: list[list[str]] = []

    class _StubProductionEmbedder:
        def embed_texts(self, texts: list[str]) -> list[tuple[float, ...]]:
            calls.append(texts)
            return [(1.0, 0.0) for _ in texts]

    monkeypatch.setattr(
        "app.services.rag.policy.evaluation.openai_embedder_from_settings",
        lambda: _StubProductionEmbedder(),
    )

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
            production=True,
            parse=lambda _: next(iter(documents.values())),
        )

    assert report.recall == 1.0
    assert calls


def test_local_policy_eval_dataset_has_product_scale_cases() -> None:
    raw = json.loads(EVAL_FIXTURE.read_text(encoding="utf-8"))
    cases = raw["cases"]
    case_ids = [case["id"] for case in cases]

    assert len(cases) >= 50
    assert len(case_ids) == len(set(case_ids))


def test_local_policy_eval_dataset_does_not_contain_sample_pii() -> None:
    rendered = EVAL_FIXTURE.read_text(encoding="utf-8")
    blocked_terms = (
        "테스트고객A",
        "TESTBIRTH-A",
        "POLICY-TEST-MASKED-001",
        "POLICY-TEST-LOCAL-002",
        "POLICY-TEST-MASKED-003",
        "POLICY-TEST-LOCAL-004",
        "TEST-PLATE-002",
        "1688-1688",
    )

    assert not any(term in rendered for term in blocked_terms)
