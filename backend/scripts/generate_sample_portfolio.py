"""Generate the immutable sample portfolio fixture from fictional PDFs."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID

from app.core.config import get_settings
from app.modules.policy.coverage.service import extract_coverages
from app.modules.policy.isolated_parsing import parse_document_isolated
from app.modules.policy.pipeline import PipelineResult, policy_sensitive_values
from app.modules.policy.schemas import PolicyParseResponse
from app.modules.policy.summary.service import extract_policy_summary
from app.modules.portfolio.overview import attach_summary_overview
from app.modules.portfolio.sample.fixture import (
    SAMPLE_FIXTURE_SCHEMA_VERSION,
    SAMPLE_GENERATOR_VERSION,
    SAMPLE_PORTFOLIO_VERSION,
    SampleAnalysisFixture,
    SamplePolicyFixture,
    SamplePortfolioFixture,
    SampleRagChunk,
)
from app.modules.portfolio.schemas import DeathBenefitGuideInput
from app.modules.portfolio.session.policy_projection import policy_for_storage
from app.modules.portfolio.summary import summarize_portfolio_coverages
from app.rag.embeddings import openai_embedder_from_settings
from app.rag.policy.indexing import build_policy_vector_records

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_SOURCE_DIR = REPOSITORY_ROOT / "sample_policy"
FIXTURE_PATH = (
    REPOSITORY_ROOT
    / "backend"
    / "app"
    / "modules"
    / "portfolio"
    / "sample"
    / "sample-portfolio.json"
)
SAMPLE_PDF_NAMES = (
    "01_건강보험_기본형.pdf",
    "02_건강보험_추가형.pdf",
    "03_자동차_운전자_복합보험.pdf",
    "04_여행_화재_복합보험.pdf",
)
DEATH_BENEFIT_CONTEXTS = (
    DeathBenefitGuideInput(),
    DeathBenefitGuideInput(has_dependent_family=True),
    DeathBenefitGuideInput(has_minor_children=True),
    DeathBenefitGuideInput(has_major_debt=True),
)
_FIXTURE_TIME = datetime(2000, 1, 1, tzinfo=UTC)


def main() -> None:
    settings = get_settings()
    embedder = openai_embedder_from_settings()
    policy_fixtures: list[SamplePolicyFixture] = []
    stored_policies = []

    for index, file_name in enumerate(SAMPLE_PDF_NAMES, start=1):
        source_path = SAMPLE_SOURCE_DIR / file_name
        pdf_bytes = source_path.read_bytes()
        document = parse_document_isolated(pdf_bytes)
        summary = extract_policy_summary(document.text)
        coverages, status = extract_coverages(document)
        document_id = UUID(int=index)
        pipeline_result = cast(
            PipelineResult,
            {
                "기본정보": summary,
                "보장목록": coverages,
                "분석상태": status,
                "policy_terms_status": "available",
                "문자수": len(document.text),
            },
        )
        response = PolicyParseResponse.model_validate(
            {
                "status": "accepted",
                "document_id": document_id,
                **pipeline_result,
            }
        )
        records = build_policy_vector_records(
            document,
            session_id=f"sample-fixture-{index}",
            created_at=_FIXTURE_TIME,
            expires_at=_FIXTURE_TIME,
            embedder=embedder,
            sensitive_values=policy_sensitive_values(summary),
        )
        policy_fixtures.append(
            SamplePolicyFixture(
                file_name=file_name,
                source_sha256=hashlib.sha256(pdf_bytes).hexdigest(),
                result=response,
                rag_chunks=[
                    SampleRagChunk(
                        text=record.chunk.text,
                        content_type=record.chunk.content_type,
                        table_index=record.chunk.table_index,
                        embedding=list(record.embedding),
                    )
                    for record in records
                ],
            )
        )
        stored_policies.append(policy_for_storage(pipeline_result, document_id=document_id.hex))

    analyses = [
        SampleAnalysisFixture(
            death_benefit_context=context,
            result=attach_summary_overview(summarize_portfolio_coverages(stored_policies, context)),
        )
        for context in DEATH_BENEFIT_CONTEXTS
    ]
    fixture = SamplePortfolioFixture(
        schema_version=SAMPLE_FIXTURE_SCHEMA_VERSION,
        portfolio_version=SAMPLE_PORTFOLIO_VERSION,
        generator_version=SAMPLE_GENERATOR_VERSION,
        embedding_model=settings.openai_embedding_model,
        embedding_dimensions=settings.openai_embedding_dimensions,
        policies=policy_fixtures,
        analyses=analyses,
    )
    FIXTURE_PATH.write_text(
        fixture.model_dump_json(indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
