"""Turn the immutable fixture into one isolated runtime sample session."""

from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import UUID

from app.modules.policy.pipeline import PipelineResult
from app.modules.policy.schemas import PolicyParseResponse
from app.modules.portfolio.sample.fixture import (
    SamplePortfolioFixture,
    SampleRagChunk,
)
from app.modules.portfolio.schemas import DeathBenefitGuideInput, PortfolioSummaryRequest
from app.modules.portfolio.session.analysis import analysis_context_hash
from app.modules.portfolio.session.models import (
    CachedPortfolioAnalysis,
    StoredPolicyDocument,
)
from app.modules.portfolio.session.policy_projection import policy_for_storage
from app.rag.policy.models import PolicyChunk, PolicyVectorRecord


@dataclass(frozen=True)
class PreparedSamplePortfolio:
    documents: tuple[StoredPolicyDocument, ...]
    analyses: tuple[CachedPortfolioAnalysis, ...]
    rag_records: tuple[PolicyVectorRecord, ...]
    public_documents: tuple[tuple[str, PolicyParseResponse], ...]


def prepare_sample_portfolio(
    fixture: SamplePortfolioFixture,
    *,
    document_ids: tuple[str, ...],
    rag_session_ids: tuple[str, ...],
    created_at: datetime,
    expires_at: datetime,
) -> PreparedSamplePortfolio:
    if len(document_ids) != len(fixture.policies) or len(rag_session_ids) != len(fixture.policies):
        raise ValueError("Sample runtime identifiers do not match the fixture")

    id_mapping: dict[str, str] = {}
    documents: list[StoredPolicyDocument] = []
    public_documents: list[tuple[str, PolicyParseResponse]] = []
    rag_records: list[PolicyVectorRecord] = []

    for policy_fixture, document_id, rag_session_id in zip(
        fixture.policies,
        document_ids,
        rag_session_ids,
        strict=True,
    ):
        canonical_id = policy_fixture.result.document_id
        id_mapping[canonical_id.hex] = document_id
        id_mapping[str(canonical_id)] = document_id
        public_result = policy_fixture.result.model_copy(
            update={"document_id": UUID(hex=document_id)}
        )
        pipeline_result = cast(
            PipelineResult,
            {
                "기본정보": public_result.기본정보.model_dump(exclude_none=True),
                "보장목록": [
                    coverage.model_dump(exclude_none=True) for coverage in public_result.보장목록
                ],
                "분석상태": public_result.분석상태,
                "policy_terms_status": public_result.policy_terms_status,
                "문자수": public_result.문자수,
            },
        )
        documents.append(
            StoredPolicyDocument(
                id=document_id,
                policy=policy_for_storage(pipeline_result, document_id=document_id),
                rag_session_id=rag_session_id,
            )
        )
        public_documents.append((policy_fixture.file_name, public_result))
        rag_records.extend(
            _runtime_rag_records(
                policy_fixture.rag_chunks,
                rag_session_id=rag_session_id,
                created_at=created_at,
                expires_at=expires_at,
            )
        )

    analyses = tuple(
        _runtime_analysis(
            analysis_fixture.death_benefit_context,
            analysis_fixture.result.model_dump(mode="json"),
            document_ids=document_ids,
            id_mapping=id_mapping,
            version=fixture.portfolio_version,
        )
        for analysis_fixture in fixture.analyses
    )
    return PreparedSamplePortfolio(
        documents=tuple(documents),
        analyses=analyses,
        rag_records=tuple(rag_records),
        public_documents=tuple(public_documents),
    )


def _runtime_rag_records(
    chunks: list[SampleRagChunk],
    *,
    rag_session_id: str,
    created_at: datetime,
    expires_at: datetime,
) -> list[PolicyVectorRecord]:
    records: list[PolicyVectorRecord] = []
    for index, chunk in enumerate(chunks, start=1):
        records.append(
            PolicyVectorRecord(
                chunk=PolicyChunk(
                    id=f"{rag_session_id}:{index}",
                    session_id=rag_session_id,
                    text=chunk.text,
                    content_type=chunk.content_type,
                    chunk_index=index,
                    table_index=chunk.table_index,
                    created_at=created_at,
                    expires_at=expires_at,
                ),
                embedding=tuple(chunk.embedding),
            )
        )
    return records


def _runtime_analysis(
    context: DeathBenefitGuideInput,
    result: dict[str, object],
    *,
    document_ids: tuple[str, ...],
    id_mapping: dict[str, str],
    version: int,
) -> CachedPortfolioAnalysis:
    request = PortfolioSummaryRequest.model_validate(
        {
            "portfolioSessionToken": "fixture-token",
            "policyIds": document_ids,
            "death_benefit_context": context,
        }
    )
    return CachedPortfolioAnalysis(
        version=version,
        context_hash=analysis_context_hash(request),
        result=cast(dict[str, object], _replace_policy_ids(result, id_mapping)),
    )


def _replace_policy_ids(value: object, mapping: dict[str, str]) -> object:
    if isinstance(value, str):
        return mapping.get(value, value)
    if isinstance(value, list):
        return [_replace_policy_ids(item, mapping) for item in value]
    if isinstance(value, dict):
        return {key: _replace_policy_ids(item, mapping) for key, item in value.items()}
    return value
