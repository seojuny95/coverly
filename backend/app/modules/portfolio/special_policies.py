"""Special non-life policy analysis for the portfolio page."""

from dataclasses import dataclass

from app.modules.portfolio.amounts import normalize, normalized_terms
from app.modules.portfolio.schemas import (
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

_AUTO_POLICY_COVERAGE_TERMS = (
    "대인배상",
    "대물배상",
    "자기차량손해",
    "자기차량",
    "자차",
    "자기신체사고",
    "자동차상해",
    "무보험자동차",
    "무보험차상해",
    "무보험차에의한상해",
)
_AUTO_PRODUCT_TERMS = (
    "자동차보험",
    "개인용자동차",
    "업무용자동차",
    "영업용자동차",
    "다이렉트자동차",
    "하이카",
)
_FIRE_PRODUCT_TERMS = (
    "화재보험",
    "주택화재보험",
    "주택종합보험",
    "재물보험",
)

_SPECIAL_COVERAGE_RULES: dict[SpecialPolicyKind, tuple[tuple[str, tuple[str, ...], str], ...]] = {
    "auto": (
        (
            "상대방의 신체 피해",
            ("대인배상",),
            "사고로 다른 사람이 다치거나 사망했을 때의 배상 담보예요.",
        ),
        (
            "상대방의 재물 피해",
            ("대물배상",),
            "사고로 다른 사람의 차량이나 재물에 생긴 손해를 배상하는 담보예요.",
        ),
        (
            "운전자·탑승자 상해",
            ("자동차상해", "자기신체사고", "자손"),
            "운전자나 탑승자가 다쳤을 때를 위한 담보예요.",
        ),
        ("내 차량 손해", ("자기차량손해", "자차"), "가입 차량에 생긴 손해를 위한 담보예요."),
        (
            "무보험차 사고 상해",
            ("무보험자동차", "무보험차상해", "무보험차에의한상해"),
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
            ("화재손해", "건물화재", "가재화재", "주택화재"),
            "화재로 건물이나 가재도구에 생긴 직접 손해를 위한 담보예요.",
        ),
        (
            "화재 배상책임",
            ("화재배상책임", "화재대물배상", "화재대인배상", "폭발포함배상책임"),
            "화재로 다른 사람이나 재물에 입힌 손해를 위한 담보예요.",
        ),
        (
            "임시 거주·복구 비용",
            ("임시거주", "잔존물제거", "화재복구", "복구비용"),
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
    ordered_kinds: tuple[SpecialPolicyKind, ...] = (
        "auto",
        "driver",
        "travel",
        "fire",
    )
    for kind in ordered_kinds:
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
    if not missing:
        return (
            f"{', '.join(confirmed)}이 모두 확인돼요. 다만 지급 범위와 한도, "
            "면책 조건은 각 증권과 약관을 더 확인해야 해요."
        )
    return (
        f"{', '.join(confirmed)}은 확인돼요. {', '.join(missing)}은 현재 자료에서 "
        "찾지 못했으며, 이것만으로 미가입이라고 단정할 수는 없어요."
    )


def _special_policy_matches(policy: PolicyInput) -> tuple[_SpecialPolicyMatch, ...]:
    category = normalize(policy.기본정보.보험분류 or "")
    product = normalize(policy.기본정보.상품명 or "")
    tags = tuple(normalize(tag) for tag in _product_tags(policy))
    tags_text = " ".join(tags)
    identity = f"{category} {product} {tags_text}"
    coverage_names = [normalize(coverage.담보명) for coverage in policy.보장목록]

    matches: list[_SpecialPolicyMatch] = []
    if (
        normalize("자동차보험") in category
        or any(term in product for term in normalized_terms(_AUTO_PRODUCT_TERMS))
        or any(normalize("자동차") in tag or normalize("자동차보험") in tag for tag in tags)
    ):
        matches.append(
            _SpecialPolicyMatch(
                "auto",
                "보험분류, 상품명 또는 상품태그에서 자동차보험 성격이 확인돼요.",
            )
        )
    elif _has_auto_policy_coverages(category, tags, coverage_names):
        matches.append(
            _SpecialPolicyMatch(
                "auto",
                "손해보험 증권 안에서 대인배상, 대물배상, 자차처럼 자동차보험 담보명이 확인돼요.",
            )
        )
    if "운전자" in identity and _is_damage_policy_identity(category, tags):
        matches.append(
            _SpecialPolicyMatch(
                "driver",
                "손해보험 증권 안에서 운전자보험 상품명 또는 태그가 확인돼요.",
            )
        )
    if (
        "여행자" in identity or "여행보험" in identity or "해외여행" in identity
    ) and _is_damage_policy_identity(category, tags):
        matches.append(
            _SpecialPolicyMatch(
                "travel",
                "손해보험 증권 안에서 여행자보험 상품명 또는 태그가 확인돼요.",
            )
        )
    if _is_fire_policy(category, product, tags, coverage_names):
        matches.append(
            _SpecialPolicyMatch(
                "fire",
                "손해보험 증권 안에서 화재, 주택, 재물 손해 관련 상품명이나 담보명이 확인돼요.",
            )
        )
    return tuple(dict.fromkeys(matches))


def _has_auto_policy_coverages(
    category: str,
    tags: tuple[str, ...],
    coverage_names: list[str],
) -> bool:
    """Infer auto insurance from auto-policy-specific coverage names only.

    Driver policies often contain words like "자동차사고" in fine/legal-cost
    coverages, so this intentionally uses mandatory/typical auto insurance
    coverage names instead of the broad word "자동차".
    """

    if not _is_damage_policy_identity(category, tags):
        return False
    terms = tuple(normalize(term) for term in _AUTO_POLICY_COVERAGE_TERMS)
    return any(any(term in name for term in terms) for name in coverage_names)


def _is_fire_policy(
    category: str,
    product: str,
    tags: tuple[str, ...],
    coverage_names: list[str],
) -> bool:
    if category in {normalize("화재보험"), normalize("주택화재보험")}:
        return True
    if any(tag in {normalize("화재보험"), normalize("주택화재보험")} for tag in tags):
        return True
    if any(term in product for term in normalized_terms(_FIRE_PRODUCT_TERMS)):
        return True
    if not _is_damage_policy_identity(category, tags):
        return False
    fire_terms = tuple(
        normalize(term)
        for _label, terms, _detail in _SPECIAL_COVERAGE_RULES["fire"]
        for term in terms
    )
    return any(any(term in name for term in fire_terms) for name in coverage_names)


def _classification_reasons_for(kind: SpecialPolicyKind, policies: list[PolicyInput]) -> list[str]:
    reasons = [
        match.reason
        for policy in policies
        for match in _special_policy_matches(policy)
        if match.kind == kind
    ]
    return list(dict.fromkeys(reasons))


def _is_damage_policy_identity(category: str, tags: tuple[str, ...]) -> bool:
    damage_categories = {
        normalize("손해보험"),
        normalize("자동차보험"),
        normalize("운전자보험"),
        normalize("운전자상해보험"),
        normalize("여행자보험"),
        normalize("화재보험"),
        normalize("주택화재보험"),
        normalize("배상책임보험"),
        normalize("보증보험"),
    }
    damage_tags = {
        normalize("자동차보험"),
        normalize("운전자보험"),
        normalize("여행자보험"),
        normalize("화재보험"),
        normalize("주택화재보험"),
        normalize("배상책임보험"),
        normalize("보증보험"),
    }
    return category in damage_categories or any(tag in damage_tags for tag in tags)


def _product_tags(policy: PolicyInput) -> list[str]:
    tags = policy.기본정보.상품태그
    if not isinstance(tags, list):
        return []
    return [tag for tag in tags if isinstance(tag, str)]
