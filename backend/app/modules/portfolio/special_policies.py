"""Special non-life policy analysis for the portfolio page."""

from dataclasses import dataclass

from app.modules.coverage.indemnity import is_damage_policy_context
from app.modules.portfolio.amounts import normalize
from app.modules.portfolio.damage_classification import (
    AUTO_LIABILITY_INJURY_TERMS,
    AUTO_LIABILITY_PROPERTY_TERMS,
    AUTO_OCCUPANT_INJURY_TERMS,
    AUTO_UNINSURED_INJURY_TERMS,
    AUTO_VEHICLE_DAMAGE_TERMS,
    FIRE_LIABILITY_TERMS,
    FIRE_PROPERTY_DAMAGE_TERMS,
    FIRE_RECOVERY_COST_TERMS,
    auto_policy_match_source,
    is_fire_policy,
)
from app.modules.portfolio.schemas import (
    SPECIAL_POLICY_KINDS,
    PolicyInput,
    SpecialCoverageCheck,
    SpecialPolicyAnalysis,
    SpecialPolicyKind,
)

_SPECIAL_POLICY_LABELS: dict[SpecialPolicyKind, str] = {
    "auto": "자동차보험",
    "driver": "운전자보험",
    "travel": "여행자보험",
    "fire": "화재보험",
}

_SPECIAL_COVERAGE_RULES: dict[SpecialPolicyKind, tuple[tuple[str, tuple[str, ...], str], ...]] = {
    "auto": (
        (
            "상대방의 신체 피해",
            AUTO_LIABILITY_INJURY_TERMS,
            "사고로 다른 사람이 다치거나 사망했을 때의 배상 담보예요.",
        ),
        (
            "상대방의 재물 피해",
            AUTO_LIABILITY_PROPERTY_TERMS,
            "사고로 다른 사람의 차량이나 재물에 생긴 손해를 배상하는 담보예요.",
        ),
        (
            "운전자·탑승자 상해",
            AUTO_OCCUPANT_INJURY_TERMS,
            "운전자나 탑승자가 다쳤을 때를 위한 담보예요.",
        ),
        ("내 차량 손해", AUTO_VEHICLE_DAMAGE_TERMS, "가입 차량에 생긴 손해를 위한 담보예요."),
        (
            "무보험차 사고 상해",
            AUTO_UNINSURED_INJURY_TERMS,
            "무보험 차량과의 사고로 다쳤을 때를 위한 담보예요.",
        ),
    ),
    "driver": (
        (
            "교통사고 처리 지원",
            ("교통사고처리지원금", "형사합의"),
            "형사합의가 필요한 교통사고의 비용 부담을 위한 담보예요.",
        ),
        (
            "변호사 선임 비용",
            ("변호사선임", "변호사비용"),
            "교통사고 형사 절차에서 변호사를 선임할 때를 위한 담보예요.",
        ),
        ("운전자 벌금", ("벌금",), "교통사고로 확정된 벌금 비용을 위한 담보예요."),
    ),
    "travel": (
        (
            "해외 의료비",
            ("해외의료비", "해외실손의료비", "국외의료비"),
            "여행 중 질병이나 상해로 해외에서 지출한 의료비를 위한 담보예요.",
        ),
        (
            "휴대품 손해",
            ("휴대품손해", "휴대품"),
            "여행 중 휴대품의 도난이나 파손을 위한 담보예요.",
        ),
        (
            "여행 중 배상책임",
            ("배상책임",),
            "여행 중 다른 사람이나 재물에 입힌 손해를 위한 담보예요.",
        ),
        (
            "항공기 지연·여행 취소",
            ("항공기지연", "항공편지연", "여행취소", "출발지연"),
            "항공편 지연이나 여행 취소로 생긴 약정 비용을 위한 담보예요.",
        ),
    ),
    "fire": (
        (
            "건물·가재 화재 손해",
            FIRE_PROPERTY_DAMAGE_TERMS,
            "화재로 건물이나 가재도구에 생긴 직접 손해를 위한 담보예요.",
        ),
        (
            "화재 배상책임",
            FIRE_LIABILITY_TERMS,
            "화재로 다른 사람이나 재물에 입힌 손해를 위한 담보예요.",
        ),
        (
            "임시 거주·복구 비용",
            FIRE_RECOVERY_COST_TERMS,
            "화재 뒤 임시 거주나 잔존물 제거·복구 비용을 위한 담보예요.",
        ),
    ),
}


@dataclass(frozen=True)
class _SpecialPolicyMatch:
    kind: SpecialPolicyKind
    reason: str


def build_special_policy_analyses(policies: list[PolicyInput]) -> list[SpecialPolicyAnalysis]:
    """Return analyses only for special policy types actually present."""

    grouped: dict[SpecialPolicyKind, list[PolicyInput]] = {
        "auto": [],
        "driver": [],
        "travel": [],
        "fire": [],
    }
    for policy in policies:
        for match in _special_policy_matches(policy):
            grouped[match.kind].append(policy)

    analyses: list[SpecialPolicyAnalysis] = []
    for kind in SPECIAL_POLICY_KINDS:
        matched = grouped[kind]
        if not matched:
            continue
        product_names = sorted({policy.기본정보.상품명 or "상품명 미확인" for policy in matched})
        coverage_names = sorted(
            {
                coverage.담보명
                for policy in matched
                for coverage in policy.보장목록
                if coverage.담보명.strip()
            }
        )
        coverage_checks = _build_special_coverage_checks(kind, coverage_names)
        classification_reasons = _classification_reasons_for(kind, matched)
        analyses.append(
            SpecialPolicyAnalysis(
                kind=kind,
                label=_SPECIAL_POLICY_LABELS[kind],
                policy_count=len(matched),
                product_names=product_names,
                confirmed_coverage_names=coverage_names,
                classification_reasons=classification_reasons,
                overview=_special_policy_overview(coverage_checks),
                coverage_checks=coverage_checks,
            )
        )
    return analyses


def _build_special_coverage_checks(
    kind: SpecialPolicyKind, coverage_names: list[str]
) -> list[SpecialCoverageCheck]:
    checks: list[SpecialCoverageCheck] = []
    for label, terms, detail in _SPECIAL_COVERAGE_RULES[kind]:
        normalized_rule_terms = tuple(normalize(term) for term in terms)
        matched_names = [
            name
            for name in coverage_names
            if any(term in normalize(name) for term in normalized_rule_terms)
        ]
        checks.append(
            SpecialCoverageCheck(
                label=label,
                status="confirmed" if matched_names else "not_found",
                detail=detail,
                matched_coverage_names=matched_names,
            )
        )
    return checks


def _special_policy_overview(checks: list[SpecialCoverageCheck]) -> str:
    confirmed = [check.label for check in checks if check.status == "confirmed"]
    missing = [check.label for check in checks if check.status == "not_found"]
    if not confirmed:
        return (
            "담보명은 확인됐지만 주요 보장 영역과 연결되는 항목은 현재 자료에서 "
            "찾지 못했어요. 실제 가입 여부는 증권 원문을 더 확인해야 해요."
        )
    # Labels are followed by punctuation, never a 조사: which label lands last in
    # the join depends on the uploaded policy, and a 한글 particle changes with
    # the syllable before it ("내 차량 손해이 모두 확인돼요").
    if not missing:
        return (
            f"모두 확인된 항목이에요: {', '.join(confirmed)}. 다만 지급 범위와 한도, "
            "면책 조건은 각 증권과 약관을 더 확인해야 해요."
        )
    return (
        f"확인된 항목이에요: {', '.join(confirmed)}. 현재 자료에서 찾지 못한 항목이에요: "
        f"{', '.join(missing)}. 이것만으로 미가입이라고 단정할 수는 없어요."
    )


def _special_policy_matches(policy: PolicyInput) -> tuple[_SpecialPolicyMatch, ...]:
    category = normalize(policy.기본정보.보험분류 or "")
    product = normalize(policy.기본정보.상품명 or "")
    tags = tuple(normalize(tag) for tag in _product_tags(policy))
    tags_text = " ".join(tags)
    identity = f"{category} {product} {tags_text}"

    matches: list[_SpecialPolicyMatch] = []
    auto_match_source = auto_policy_match_source(policy)
    if auto_match_source == "identity":
        matches.append(
            _SpecialPolicyMatch(
                "auto",
                "보험분류, 상품명 또는 상품태그에서 자동차보험 성격이 확인돼요.",
            )
        )
    elif auto_match_source == "coverage":
        matches.append(
            _SpecialPolicyMatch(
                "auto",
                "손해보험 증권 안에서 대인배상, 대물배상, 자차처럼 자동차보험 담보명이 확인돼요.",
            )
        )
    if "운전자" in identity and is_damage_policy_context(policy):
        matches.append(
            _SpecialPolicyMatch(
                "driver",
                "손해보험 증권 안에서 운전자보험 상품명 또는 태그가 확인돼요.",
            )
        )
    if (
        "여행자" in identity or "여행보험" in identity or "해외여행" in identity
    ) and is_damage_policy_context(policy):
        matches.append(
            _SpecialPolicyMatch(
                "travel",
                "손해보험 증권 안에서 여행자보험 상품명 또는 태그가 확인돼요.",
            )
        )
    if is_fire_policy(policy):
        matches.append(
            _SpecialPolicyMatch(
                "fire",
                "손해보험 증권 안에서 화재, 주택, 재물 손해 관련 상품명이나 담보명이 확인돼요.",
            )
        )
    return tuple(dict.fromkeys(matches))


def _classification_reasons_for(kind: SpecialPolicyKind, policies: list[PolicyInput]) -> list[str]:
    reasons = [
        match.reason
        for policy in policies
        for match in _special_policy_matches(policy)
        if match.kind == kind
    ]
    return list(dict.fromkeys(reasons))


def _product_tags(policy: PolicyInput) -> list[str]:
    tags = policy.기본정보.상품태그
    if not isinstance(tags, list):
        return []
    return [tag for tag in tags if isinstance(tag, str)]
