import json
from pathlib import Path

import pytest

from app.services.llm import JsonCompleter
from app.services.policy.classification import CLASSIFICATION_UNKNOWN, classify_policy

_RULES_PATH = (
    Path(__file__).resolve().parents[1] / "app" / "services" / "data" / "classification_rules.json"
)

_MAGIC_NUMBER_KEYS = {
    "product_weight",
    "min_strength",
    "min_product_hits",
    "min_combined_strength",
    "product_bonus",
}


def _forbidden_completer(_system: str, _user: str) -> dict[str, object]:
    raise AssertionError("LLM fallback must not be called when a deterministic term matches")


@pytest.mark.parametrize(
    ("product_name", "text", "expected_classification"),
    [
        ("삼성 개인용자동차보험", "자동차보험 대인배상 대물배상 자기차량손해", "자동차"),
        ("주택화재보험", "화재손해 화재배상책임", "배상·화재·기타"),
        ("메리츠 실비보험", "실손의료비 급여 비급여 자기부담금 보상", "상해·질병·실손"),
        ("무배당 연금보험", "연금개시 연금수령", "생명·연금"),
        ("무배당 교보New종신보험", "사망보험금 해약환급금 20년납 종신", "생명·연금"),
        (
            "무배당 참좋은운전자상해보험",
            "교통사고처리지원금 자동차부상치료비 벌금",
            "배상·화재·기타",
        ),
    ],
)
def test_classify_policy_deterministic_match_never_calls_llm(
    product_name: str, text: str, expected_classification: str
) -> None:
    result = classify_policy(text=text, product_name=product_name, complete=_forbidden_completer)

    assert result["보험분류"] == expected_classification


def test_classify_policy_matches_driver_accident_product_without_llm() -> None:
    result = classify_policy(
        text="교통사고처리지원금 자동차부상치료비 벌금",
        product_name="무배당 참좋은운전자상해보험",
        complete=_forbidden_completer,
    )

    assert result["보험분류"] == "배상·화재·기타"
    assert "운전자" in result["상품태그"]


def test_classify_policy_falls_back_to_llm_when_no_official_term_matches() -> None:
    calls: list[tuple[str, str]] = []

    def fake_completer(system: str, user: str) -> dict[str, object]:
        calls.append((system, user))
        return {"보험분류": "상해·질병·실손", "상품태그": []}

    result = classify_policy(
        text="이 상품은 다양한 위험을 폭넓게 보장합니다.",
        product_name="무배당 든든한 종합보장 플랜",
        complete=fake_completer,
    )

    assert result["보험분류"] == "상해·질병·실손"
    assert len(calls) == 1


def test_classify_policy_returns_unknown_when_llm_fallback_raises() -> None:
    def raising_completer(_system: str, _user: str) -> dict[str, object]:
        raise RuntimeError("LLM unavailable")

    result = classify_policy(
        text="이 상품은 다양한 위험을 폭넓게 보장합니다.",
        product_name="무배당 든든한 종합보장 플랜",
        complete=raising_completer,
    )

    assert result == {"보험분류": CLASSIFICATION_UNKNOWN, "상품태그": []}


def test_classify_policy_adds_tags_from_tag_terms_sorted_by_tag_order() -> None:
    result = classify_policy(
        text="""
        무배당 흥국화재 맘편한 자녀사랑보험
        암진단비, 질병입원일당, 후유장해, 어린이보험
        """,
        product_name="무배당 흥국화재 맘편한 자녀사랑보험 상해보험",
        complete=_forbidden_completer,
    )

    assert result["보험분류"] == "상해·질병·실손"
    assert result["상품태그"] == ["암", "상해", "질병", "어린이"]


def test_classification_rules_json_has_no_magic_number_fields() -> None:
    raw = json.loads(_RULES_PATH.read_text(encoding="utf-8"))

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                assert key not in _MAGIC_NUMBER_KEYS, f"magic-number field found: {key}"
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(raw)


def test_classify_policy_signature_accepts_json_completer_type() -> None:
    completer: JsonCompleter = _forbidden_completer
    result = classify_policy(
        text="자동차보험 대인배상", product_name="자동차보험", complete=completer
    )

    assert result["보험분류"] == "자동차"
