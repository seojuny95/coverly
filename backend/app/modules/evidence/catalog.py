"""Shared grounding helpers for portfolio analysis and Q&A."""

from dataclasses import dataclass

from app.modules.consultation.contracts import ConsultationEvidence, InsuredDemographics
from app.modules.consultation.safety import (
    filter_safe_unique_texts as filter_safe_unique_texts,
)
from app.modules.consultation.safety import (
    has_unsupported_conclusion as has_unsupported_conclusion,
)
from app.modules.consultation.safety import (
    is_safe_analysis_text as is_safe_analysis_text,
)
from app.modules.consultation.safety import (
    is_safe_confirmed_fact as is_safe_confirmed_fact,
)
from app.modules.consultation.safety import (
    is_safe_general_guidance as is_safe_general_guidance,
)
from app.modules.coverage.taxonomy import classify_coverage
from app.modules.portfolio.schemas import CoverageSourceItem, PolicyInput
from app.modules.portfolio.summary import PortfolioFacts
from app.rag.policy import PolicyRetrievalHit


@dataclass(frozen=True)
class EvidenceCatalog:
    """Indexed consultation facts plus category lookup for deterministic citations."""

    items: tuple[ConsultationEvidence, ...]
    by_id: dict[str, ConsultationEvidence]
    coverage_ids_by_category: dict[str, tuple[str, ...]]


def with_session_evidence(
    catalog: EvidenceCatalog, hits: list[PolicyRetrievalHit]
) -> EvidenceCatalog:
    """Append ephemeral uploaded-document chunks to the consultation catalog."""
    if not hits:
        return catalog
    items = list(catalog.items)
    for index, hit in enumerate(hits, start=1):
        items.append(
            ConsultationEvidence(
                id=f"session:{index}",
                fact=f"업로드 증권 원문 발췌: {hit.chunk.text}",
            )
        )
    return EvidenceCatalog(
        items=tuple(items),
        by_id={item.id: item for item in items},
        coverage_ids_by_category=catalog.coverage_ids_by_category,
    )


def build_evidence_catalog(
    facts: PortfolioFacts,
    demographics: InsuredDemographics,
    missing_categories: tuple[str, ...] = (),
    auto_policies: tuple[PolicyInput, ...] = (),
) -> EvidenceCatalog:
    """Build the only policy facts that an LLM is allowed to cite.

    `auto_policies` are excluded from the analysis aggregates but surfaced here
    so Q&A knows the user's auto coverage exists (accident help, claim channel).
    """

    items: list[ConsultationEvidence] = []
    category_ids: dict[str, list[str]] = {}

    items.append(
        ConsultationEvidence(
            id="portfolio:summary",
            fact=(
                f"비자동차 보험 {len(facts.policies)}건, "
                f"확인 가능한 정액형 담보 {len(facts.coverage_summary.totals)}종"
            ),
        )
    )

    demographic_fact = _demographic_fact(demographics)
    if demographic_fact:
        items.append(ConsultationEvidence(id="demographics", fact=demographic_fact))

    for index, policy in enumerate(facts.policies, start=1):
        insurer = policy.기본정보.보험사
        product = policy.기본정보.상품명
        classification = policy.기본정보.보험분류 or "미분류"
        label = " · ".join(item for item in (insurer, product) if item) or "상품 정보 미확인"
        items.append(
            ConsultationEvidence(
                id=f"policy:{index}",
                fact=f"{label} ({classification}) 가입 사실 확인",
                policy_id=policy.id,
                insurer=insurer,
                product_name=product,
            )
        )

    for index, total in enumerate(facts.coverage_summary.totals, start=1):
        evidence_id = f"coverage:{index}"
        source = total.composition[0]
        duplicate_detail = _fixed_coverage_duplicate_detail(total.composition)
        items.append(
            ConsultationEvidence(
                id=evidence_id,
                fact=(
                    f"{total.display_name} 가입금액 합계 {total.total_amount:,}원 확인 "
                    "(지급 성격: 정액형)"
                    f"{duplicate_detail}"
                ),
                policy_id=source.policy_id if len(total.composition) == 1 else None,
                insurer=source.insurer if len(total.composition) == 1 else None,
                product_name=source.product_name if len(total.composition) == 1 else None,
                coverage_name=total.display_name,
                amount=total.total_amount,
            )
        )
        category = classify_coverage(total.display_name)
        if category:
            category_ids.setdefault(category, []).append(evidence_id)

    damage_evidence_keys = {
        (
            damage_policy.policy_id,
            damage_policy.insurer,
            damage_policy.product_name,
            coverage.coverage_name,
        )
        for group in facts.coverage_summary.damage_coverages
        for damage_policy in group.policies
        for coverage in damage_policy.coverages
    }
    for index, actual_loss in enumerate(
        facts.coverage_summary.actual_loss_coverages,
        start=1,
    ):
        evidence_key = (
            actual_loss.policy_id,
            actual_loss.insurer,
            actual_loss.product_name,
            actual_loss.coverage_name,
        )
        if actual_loss.is_damage_policy and evidence_key in damage_evidence_keys:
            continue

        evidence_id = f"actual-loss:{index}"
        coverage_type = "실손의료비" if actual_loss.is_medical_indemnity else "실손형"
        duplicate_detail = (
            ", 여러 계약에서 같은 실손형 담보 확인"
            if actual_loss.duplicate_across_contracts
            else ""
        )
        items.append(
            ConsultationEvidence(
                id=evidence_id,
                fact=(
                    f"{actual_loss.coverage_name} 가입 사실 확인 "
                    f"(지급 성격: {coverage_type}{duplicate_detail})"
                ),
                policy_id=actual_loss.policy_id,
                insurer=actual_loss.insurer,
                product_name=actual_loss.product_name,
                coverage_name=actual_loss.coverage_name,
            )
        )
        category = classify_coverage(actual_loss.coverage_name)
        if category and actual_loss.is_medical_indemnity:
            category_ids.setdefault(category, []).append(evidence_id)

    for index, excluded in enumerate(facts.coverage_summary.excluded_coverages, start=1):
        items.append(
            ConsultationEvidence(
                id=f"excluded:{index}",
                fact=f"{excluded.coverage_name}: {excluded.reason}",
                policy_id=excluded.policy_id,
                coverage_name=excluded.coverage_name,
            )
        )

    damage_index = 1
    for group in facts.coverage_summary.damage_coverages:
        for damage_policy in group.policies:
            label = (
                " · ".join(
                    item for item in (damage_policy.insurer, damage_policy.product_name) if item
                )
                or "상품 정보 미확인"
            )
            for coverage in damage_policy.coverages:
                amount = f" 가입금액 {coverage.original_amount}" if coverage.original_amount else ""
                items.append(
                    ConsultationEvidence(
                        id=f"damage:{damage_index}",
                        fact=(
                            f"{label} ({group.insurance_type}) "
                            f"{coverage.coverage_name}{amount} 확인"
                        ),
                        policy_id=damage_policy.policy_id,
                        insurer=damage_policy.insurer,
                        product_name=damage_policy.product_name,
                        coverage_name=coverage.coverage_name,
                    )
                )
                damage_index += 1

    for index, category in enumerate(missing_categories, start=1):
        items.append(
            ConsultationEvidence(
                id=f"gap:{index}",
                fact=f"업로드된 비자동차 보험 전체에서 {category} 담보를 확인하지 못함",
                coverage_name=category,
            )
        )

    for index, policy in enumerate(auto_policies, start=1):
        insurer = policy.기본정보.보험사
        product = policy.기본정보.상품명
        label = " · ".join(item for item in (insurer, product) if item) or "상품 정보 미확인"
        coverage_names = [coverage.담보명 for coverage in policy.보장목록 if coverage.담보명]
        detail = f" (보장: {', '.join(coverage_names)})" if coverage_names else ""
        items.append(
            ConsultationEvidence(
                id=f"auto:{index}",
                fact=f"{label} 자동차보험 가입 사실 확인{detail}",
                policy_id=policy.id,
                insurer=insurer,
                product_name=product,
            )
        )

    if not any(
        term in item.fact for item in items for term in ("같은 담보명", "여러 계약에서 같은 실손형")
    ):
        items.append(
            ConsultationEvidence(
                id="portfolio:no-overlap",
                fact=(
                    "업로드된 증권 전체에서 동일하게 정규화된 정액형 담보나 "
                    "여러 계약의 같은 실손형 담보를 확인하지 못함"
                ),
            )
        )

    return EvidenceCatalog(
        items=tuple(items),
        by_id={item.id: item for item in items},
        coverage_ids_by_category={category: tuple(ids) for category, ids in category_ids.items()},
    )


def _fixed_coverage_duplicate_detail(composition: list[CoverageSourceItem]) -> str:
    if len(composition) < 2:
        return ""

    amount_labels: list[str] = []
    for source in composition:
        label = " · ".join(item for item in (source.insurer, source.product_name) if item)
        amount_label = f"{label} {source.amount:,}원" if label else f"{source.amount:,}원"
        amount_labels.append(amount_label)
    source_detail = f" (구성: {', '.join(amount_labels)})"
    return f", {len(composition)}개 증권에서 같은 담보명 확인{source_detail}"


def valid_evidence_ids(evidence_ids: list[str], catalog: EvidenceCatalog) -> tuple[str, ...] | None:
    """Require every cited id to exist; partial citation repair could hide hallucinations."""

    unique = tuple(dict.fromkeys(evidence_ids))
    if not unique or any(evidence_id not in catalog.by_id for evidence_id in unique):
        return None
    return unique


def _demographic_fact(demographics: InsuredDemographics) -> str | None:
    parts: list[str] = []
    if demographics.age is not None:
        parts.append(f"만 {demographics.age}세")
    if demographics.gender != "미상":
        parts.append(demographics.gender)
    if not parts:
        return None
    source_label = {
        "policy": "증권에서 확인",
        "user": "사용자 입력",
        "unknown": "출처 미확인",
    }[demographics.source]
    return f"피보험자 {' · '.join(parts)} ({source_label})"
