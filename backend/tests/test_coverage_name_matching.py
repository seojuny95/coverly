import json
from dataclasses import replace
from pathlib import Path

import pytest

from app.services.coverage_knowledge.matching import (
    canonicalize_coverage_name,
    choose_display_name,
    match_coverage_names,
    query_contains_canonical_name,
)
from app.services.coverage_knowledge.rules import default_matching_rules, load_matching_rules


@pytest.mark.parametrize(
    ("left", "right", "expected_kind", "expected_display"),
    [
        (
            "뇌혈관질환진단비",
            "뇌혈관질환진단비(감액없음)",
            "exact",
            "뇌혈관질환진단비",
        ),
        (
            "암진단비(유사암제외)",
            "암진단비(유사암제외)(감액없음)",
            "exact",
            "암진단비(유사암제외)",
        ),
        (
            "유사암진단비(감액없음)",
            "유사암진담비",
            "exact",
            "유사암진단비",
        ),
        (
            "허혈성심장질환진단비",
            "허혈성심질환진단비(감액없음)",
            "curated_alias",
            "허혈성심질환진단비",
        ),
    ],
)
def test_curated_positive_pairs_are_mergeable(
    left: str, right: str, expected_kind: str, expected_display: str
) -> None:
    decision = match_coverage_names(left, right)

    assert decision.mergeable is True
    assert decision.kind == expected_kind
    assert choose_display_name([right, left]) == expected_display
    assert decision.left.original_name == left
    assert decision.right.original_name == right


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("암진단비", "유사암진단비"),
        ("암진단비", "암수술비"),
        ("암진단비", "암재진단비"),
        ("상해후유장해", "질병후유장해"),
        ("일반상해후유장해(80%이상)", "일반상해후유장해(3~79%)"),
    ],
)
def test_protected_term_differences_are_hard_distinct(left: str, right: str) -> None:
    decision = match_coverage_names(left, right)

    assert decision.kind == "distinct"
    assert decision.mergeable is False
    assert decision.reason == "protected terms differ"


def test_unbalanced_parenthetical_is_not_removed() -> None:
    malformed = canonicalize_coverage_name("암진단비(감액없음")
    plain = canonicalize_coverage_name("암진단비")

    assert malformed.normalized_key != plain.normalized_key
    assert malformed.display_name == "암진단비(감액없음"


@pytest.mark.parametrize(
    "name",
    [
        "암진단비((감액없음))",
        "암진단비(감액없음 조건)",
        "암진단비[감액없음]",
    ],
)
def test_non_exact_or_non_top_level_modifiers_are_preserved(name: str) -> None:
    assert canonicalize_coverage_name(name).normalized_key != "암진단비"


def test_only_exact_safe_parenthetical_is_removed() -> None:
    safe = canonicalize_coverage_name("암진단비( 감액없음 )")
    meaningful = canonicalize_coverage_name("암진단비(유사암제외)")

    assert safe.normalized_key == "암진단비"
    assert meaningful.normalized_key == "암진단비유사암제외"


def test_configured_prefix_wrapper_is_removed_without_losing_inner_qualifiers() -> None:
    wrapped = canonicalize_coverage_name("기본계약(일반상해후유장해(80%이상))")

    assert wrapped.normalized_key == "일반상해후유장해80%이상"
    assert wrapped.display_name == "일반상해후유장해(80%이상)"


def test_nfkc_normalizes_full_width_parentheses_and_ascii() -> None:
    full_width = canonicalize_coverage_name("ＡＢＣ암진단비（감액없음）")

    assert full_width.normalized_key == "abc암진단비"
    assert full_width.original_name == "ＡＢＣ암진단비（감액없음）"


def test_canonicalization_is_idempotent_and_display_choice_is_deterministic() -> None:
    names = ["허혈성심장질환진단비", "허혈성심질환진단비(감액없음)"]
    first = canonicalize_coverage_name(names[0])
    repeated = canonicalize_coverage_name(first.display_name)

    assert repeated.normalized_key == first.normalized_key
    assert repeated.display_name == first.display_name
    assert choose_display_name(names) == choose_display_name(reversed(names))


def test_similarity_threshold_only_changes_candidate_classification() -> None:
    base_rules = default_matching_rules()
    left = "뇌혈관질환진단비A"
    right = "뇌혈관질환진단비B"
    measured = match_coverage_names(
        left,
        right,
        replace(base_rules, candidate_similarity_threshold=0),
    )

    at_boundary = match_coverage_names(
        left,
        right,
        replace(base_rules, candidate_similarity_threshold=measured.similarity),
    )
    above_boundary = match_coverage_names(
        left,
        right,
        replace(
            base_rules,
            candidate_similarity_threshold=min(1, measured.similarity + 0.0001),
        ),
    )

    assert at_boundary.kind == "candidate"
    assert at_boundary.mergeable is False
    assert above_boundary.kind == "distinct"
    assert above_boundary.mergeable is False


def test_query_matches_exact_replacement_and_curated_alias_but_never_fuzzy() -> None:
    assert query_contains_canonical_name(
        "허혈성 심장질환 진단비가 얼마인가요?", "허혈성심질환진단비"
    )
    assert query_contains_canonical_name("유사암 진담비를 확인해줘", "유사암진단비")
    assert not query_contains_canonical_name("유사암진단비를 확인해줘", "암진단비")
    assert not query_contains_canonical_name("재진단암진단비는 얼마야?", "암진단비")
    assert not query_contains_canonical_name("일반암진단비는 얼마야?", "암진단비")
    assert not query_contains_canonical_name("뇌혈관질환진단금은?", "뇌혈관질환진단비")


@pytest.mark.parametrize("threshold", [-0.01, 1.01, "high", True])
def test_config_rejects_invalid_threshold(tmp_path: Path, threshold: object) -> None:
    path = _write_rules(tmp_path, threshold=threshold)

    with pytest.raises(ValueError, match="candidate_similarity_threshold"):
        load_matching_rules(path)


def test_config_rejects_alias_collisions(tmp_path: Path) -> None:
    payload = _rules_payload()
    payload["alias_groups"] = [
        {"canonical": "첫번째", "aliases": ["겹침"]},
        {"canonical": "두번째", "aliases": ["겹침"]},
    ]
    path = tmp_path / "rules.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="multiple groups"):
        load_matching_rules(path)


def test_config_includes_canonical_without_repeating_it_in_aliases(tmp_path: Path) -> None:
    payload = _rules_payload()
    payload["alias_groups"] = [{"canonical": "정상 표시명", "aliases": []}]
    path = _write_payload(tmp_path, payload)

    rules = load_matching_rules(path)
    result = canonicalize_coverage_name("정상 표시명", rules)

    assert result.display_name == "정상 표시명"
    assert result.normalized_key == "정상표시명"


def test_config_rejects_alias_chain_or_cycle(tmp_path: Path) -> None:
    payload = _rules_payload()
    payload["alias_groups"] = [
        {"canonical": "암진단비", "aliases": ["암진단금"]},
        {"canonical": "암진단금", "aliases": ["암보장금"]},
    ]

    with pytest.raises(ValueError, match="multiple groups"):
        load_matching_rules(_write_payload(tmp_path, payload))


def test_config_rejects_alias_with_different_protected_terms(tmp_path: Path) -> None:
    payload = _rules_payload()
    payload["alias_groups"] = [
        {"canonical": "암진단비", "aliases": ["암수술비"]},
    ]

    with pytest.raises(ValueError, match="protected terms"):
        load_matching_rules(_write_payload(tmp_path, payload))


@pytest.mark.parametrize(
    "replacements",
    [
        {"진단비": "수술비", "수술비": "진단비"},
        {"---": "진단비"},
        {"진담비": "---"},
    ],
)
def test_config_rejects_replacement_cycles_or_empty_keys(
    tmp_path: Path, replacements: dict[str, str]
) -> None:
    payload = _rules_payload()
    payload["replacements"] = replacements

    with pytest.raises(ValueError, match="replacement"):
        load_matching_rules(_write_payload(tmp_path, payload))


def test_config_requires_version_and_ignored_modifiers(tmp_path: Path) -> None:
    payload = _rules_payload()
    del payload["version"]
    with pytest.raises(ValueError, match="version"):
        load_matching_rules(_write_payload(tmp_path, payload))

    payload = _rules_payload()
    del payload["ignored_parenthetical_modifiers"]
    with pytest.raises(ValueError, match="ignored modifier"):
        load_matching_rules(_write_payload(tmp_path, payload))

    payload = _rules_payload()
    del payload["ignored_prefix_wrappers"]
    with pytest.raises(ValueError, match="ignored modifier"):
        load_matching_rules(_write_payload(tmp_path, payload))


def test_display_name_requires_at_least_one_name() -> None:
    with pytest.raises(ValueError, match="at least one"):
        choose_display_name([])


def _write_rules(tmp_path: Path, *, threshold: object) -> Path:
    payload = _rules_payload()
    payload["candidate_similarity_threshold"] = threshold
    path = tmp_path / "rules.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _rules_payload() -> dict[str, object]:
    return {
        "version": 1,
        "candidate_similarity_threshold": 0.88,
        "ignored_parenthetical_modifiers": ["감액없음"],
        "ignored_prefix_wrappers": ["기본계약"],
        "replacements": {"진담비": "진단비"},
        "alias_groups": [
            {
                "canonical": "허혈성심질환진단비",
                "aliases": ["허혈성심장질환진단비"],
            }
        ],
        "protected_terms": ["유사암", "암", "재진단", "진단", "수술", "상해", "질병"],
    }


def _write_payload(tmp_path: Path, payload: dict[str, object]) -> Path:
    path = tmp_path / "rules.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path
