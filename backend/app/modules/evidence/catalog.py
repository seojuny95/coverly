"""Shared grounding helpers for portfolio analysis and Q&A."""

from collections.abc import Callable
from dataclasses import dataclass

from app.modules.coverage.taxonomy import classify_coverage
from app.modules.portfolio.schemas import PolicyInput
from app.modules.portfolio.summary import PortfolioFacts
from app.modules.qa.contracts import ConsultationEvidence, InsuredDemographics
from app.modules.qa.schemas import AnswerCitation
from app.rag.official.models import RetrievalHit
from app.rag.policy import PolicyRetrievalHit

_UNSUPPORTED_CONCLUSIONS = (
    "보험금이 지급",
    "보험금을 지급",
    "보상받을 수",
    "보상 받을 수",
    "면책이 없",
    "면책되지 않",
    "가입하면 됩니다",
    "반드시 가입",
    "공식 기준",
    "충분합니다",
    "부족합니다",
    "가족력이 있어",
    "부양가족이 있어",
    "자녀가 있어",
    "소득이 높",
    "소득이 낮",
)
_ADEQUACY_TERMS = (
    "충분",
    "부족",
    "적정",
    "권장",
    "추천",
    "최소",
    "필수",
    "무조건",
)
# Sales pushes that _DIRECT_ACTION_TERMS misses but are never acceptable — kept
# separate from adequacy words (충분/부족) that grounded analysis is allowed to use.
_SALES_PUSH_TERMS = (
    "반드시 가입",
    "꼭 가입",
    "가입하면 됩니다",
    "가입하는 것이 좋습니다",
    "추가 가입",
    "가입을 고려",
    "가입을 검토",
    "추가적인 보장",
    "필요한 보장",
)
_DIRECT_ACTION_TERMS = (
    "가입하세요",
    "가입해요",
    "가입해야",
    "해지하세요",
    "증액하세요",
    "감액하세요",
    "늘리세요",
    "줄이세요",
    "변경하세요",
)
_UNSUPPORTED_GUIDANCE_TERMS = _ADEQUACY_TERMS + (
    "늘리",
    "높이",
    "증액",
    "줄이",
    "낮추",
    "감액하",
    "가입하",
    "추가하",
    "해지하",
    "유지하",
    "바꾸",
    "변경하",
    "맞추",
    "확보하",
    "준비하",
    "좋습니다",
    "좋아요",
    "꼭 ",
)
_MONEY_UNITS = ("억원", "천만원", "백만원", "만원")
_PAYOUT_OR_OFFICIAL_CLAIMS = (
    "보험금이 지급",
    "보험금을 지급",
    "보상받을 수",
    "보상 받을 수",
    "면책이 없",
    "면책되지 않",
    "공식 기준",
)
_OFFICIAL_CLAIMS = ("공식 기준",)
_PAYOUT_CLAIMS = tuple(term for term in _PAYOUT_OR_OFFICIAL_CLAIMS if term not in _OFFICIAL_CLAIMS)
_OFFICIAL_ADEQUACY_TERMS = ("충분", "부족", "적정", "권장", "추천")
_FABRICATED_PERSONAL_FACTS = (
    "가족력이 있어",
    "부양가족이 있어",
    "자녀가 있어",
    "소득이 높",
    "소득이 낮",
)


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


def with_official_evidence(
    catalog: EvidenceCatalog, hits: tuple[RetrievalHit, ...]
) -> EvidenceCatalog:
    """Append official-source guidance as auxiliary citation evidence."""

    if not hits:
        return catalog
    items = list(catalog.items)
    for index, hit in enumerate(hits, start=1):
        chunk = hit.chunk
        label = f" ({chunk.citation_label})" if chunk.citation_label else ""
        items.append(
            ConsultationEvidence(
                id=f"official:{index}",
                fact=(
                    f"{chunk.publisher} {chunk.source_title}{label}: "
                    f"{_compact_evidence_text(chunk.text, 700)}"
                ),
                source_title=chunk.source_title,
                publisher=chunk.publisher,
                citation_label=chunk.citation_label,
            )
        )
    return EvidenceCatalog(
        items=tuple(items),
        by_id={item.id: item for item in items},
        coverage_ids_by_category=catalog.coverage_ids_by_category,
    )


def _compact_evidence_text(text: str, max_chars: int) -> str:
    compact = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 1].rstrip() + "…"


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
        items.append(
            ConsultationEvidence(
                id=evidence_id,
                fact=f"{total.display_name} 가입금액 합계 {total.total_amount:,}원 확인",
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

    for index, indemnity in enumerate(facts.coverage_summary.indemnity_coverages, start=1):
        evidence_id = f"indemnity:{index}"
        items.append(
            ConsultationEvidence(
                id=evidence_id,
                fact=f"{indemnity.coverage_name} 실손형 담보 가입 사실 확인",
                policy_id=indemnity.policy_id,
                insurer=indemnity.insurer,
                product_name=indemnity.product_name,
                coverage_name=indemnity.coverage_name,
            )
        )
        category = classify_coverage(indemnity.coverage_name)
        if category:
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

    return EvidenceCatalog(
        items=tuple(items),
        by_id={item.id: item for item in items},
        coverage_ids_by_category={category: tuple(ids) for category, ids in category_ids.items()},
    )


def has_unsupported_conclusion(text: str) -> bool:
    compact = " ".join(text.split())
    return any(term in compact for term in _UNSUPPORTED_CONCLUSIONS)


def is_safe_confirmed_fact(text: str) -> bool:
    """Allow prose facts only when they avoid new numeric or claim conclusions."""

    cleaned = text.strip()
    return (
        bool(cleaned)
        and not any(character.isdigit() for character in cleaned)
        and not has_unsupported_conclusion(cleaned)
        and not any(term in cleaned for term in _ADEQUACY_TERMS)
        and not any(term in cleaned for term in _DIRECT_ACTION_TERMS)
    )


def is_safe_general_guidance(text: str) -> bool:
    """Allow non-numeric review guidance without adequacy claims or direct actions."""

    cleaned = text.strip()
    if not cleaned or has_unsupported_conclusion(cleaned):
        return False
    if any(character.isdigit() for character in cleaned):
        return False
    if any(unit in cleaned for unit in _MONEY_UNITS):
        return False
    return not any(term in cleaned for term in _UNSUPPORTED_GUIDANCE_TERMS)


def is_safe_analysis_text(text: str, *, allow_official_claims: bool = False) -> bool:
    """Allow grounded opinion — amounts, high/low, over/under judgments — while
    still blocking sales commands, payout/exclusion verdicts, official-standard
    claims, and fabricated personal facts. Used for the richer strength/gap and
    overview analysis where adequacy opinions are intended."""

    cleaned = text.strip()
    if not cleaned:
        return False
    compact = " ".join(cleaned.split())
    blocked_claims = _PAYOUT_CLAIMS if allow_official_claims else _PAYOUT_OR_OFFICIAL_CLAIMS
    if any(term in compact for term in blocked_claims):
        return False
    if (
        allow_official_claims
        and "공식 기준" in compact
        and any(term in compact for term in _OFFICIAL_ADEQUACY_TERMS)
    ):
        return False
    if any(term in compact for term in _FABRICATED_PERSONAL_FACTS):
        return False
    if any(term in compact for term in _SALES_PUSH_TERMS):
        return False
    return not any(term in cleaned for term in _DIRECT_ACTION_TERMS)


def filter_safe_unique_texts(
    items: list[str],
    *,
    is_safe: Callable[[str], bool],
) -> list[str]:
    accepted: list[str] = []
    for item in items:
        cleaned = item.strip()
        if not is_safe(cleaned) or cleaned in accepted:
            continue
        accepted.append(cleaned)
    return accepted


def citation_from_evidence(item: ConsultationEvidence) -> AnswerCitation:
    return AnswerCitation(
        evidence_id=item.id,
        policy_id=item.policy_id,
        insurer=item.insurer,
        product_name=item.product_name,
        coverage_name=item.coverage_name,
    )


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
