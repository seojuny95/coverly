from app.schemas.consultation import InsuredDemographics
from app.schemas.portfolio import PolicyInput
from app.services.portfolio_analysis import analyze_portfolio


def _policy(policy_id: str, classification: str, coverage_name: str, amount: str) -> PolicyInput:
    return PolicyInput.model_validate(
        {
            "id": policy_id,
            "기본정보": {
                "보험사": "테스트보험",
                "상품명": f"상품-{policy_id}",
                "보험분류": classification,
            },
            "보장목록": [
                {
                    "담보명": coverage_name,
                    "가입금액": amount,
                    "지급유형": "정액",
                }
            ],
        }
    )


def test_analysis_returns_overall_and_classification_facts() -> None:
    policies = [
        _policy("p1", "질병", "암진단비", "3,000만원"),
        _policy("p2", "상해", "상해수술비", "100만원"),
    ]

    result = analyze_portfolio(policies, age=35, gender="여성")

    assert result.status == "complete"
    assert result.policy_count == 2
    assert result.classification_count == 2
    assert result.confirmed_total_amount == 31_000_000
    assert [(item.classification, item.policy_count) for item in result.classifications] == [
        ("상해", 1),
        ("질병", 1),
    ]
    assert {source.policy_id for source in result.sources} == {"p1", "p2"}


def test_analysis_honestly_reports_partial_and_empty_states() -> None:
    partial = PolicyInput.model_validate(
        {
            "id": "p1",
            "기본정보": {"보험분류": "질병"},
            "보장목록": [{"담보명": "알 수 없는 담보", "가입금액": "별도 약정"}],
        }
    )

    partial_result = analyze_portfolio([partial], age=35, gender="여성")
    empty_result = analyze_portfolio([], age=35, gender="여성")

    assert partial_result.status == "partial"
    assert partial_result.excluded_coverage_count == 1
    assert partial_result.notices
    assert empty_result.status == "empty"
    assert empty_result.policy_count == 0


def test_analysis_inherits_partial_parse_status() -> None:
    policy = _policy("p1", "질병", "암진단비", "3,000만원")
    policy.분석상태 = "부분"

    result = analyze_portfolio([policy], age=35, gender="여성")

    assert result.status == "partial"


def test_analysis_does_not_make_adequacy_claims() -> None:
    result = analyze_portfolio(
        [_policy("p1", "질병", "암진단비", "3,000만원")],
        age=35,
        gender="여성",
    )

    rendered = result.model_dump_json()
    assert "충분합니다" not in rendered
    assert "가입하세요" not in rendered


def test_analysis_accepts_only_cited_llm_insights_and_builds_amount_from_fact() -> None:
    policy = _policy("p1", "질병", "암진단비", "3,000만원")

    def complete(_: str, user: str) -> dict[str, object]:
        assert '"age":35' in user
        assert '"id":"coverage:1"' in user
        return {
            "strengths": [
                {
                    "title": "암 진단 담보가 확인돼요",
                    "detail": "현재 증권에서 가입 사실을 확인했습니다.",
                    "evidence_ids": ["coverage:1"],
                }
            ],
            "gaps": [],
            "amount_review_items": [
                {
                    "coverage_evidence_id": "coverage:1",
                    "title": "생활비 기준으로 다시 살펴보세요",
                    "guidance": "일반 가이드로 검토하되 개인 예산을 함께 보세요.",
                    "rationale": "증권만으로 개인별 필요 금액을 확정할 수 없어요.",
                    "suggested_range": "공식 기준이 아닌 낮은 확신의 참고 범위",
                }
            ],
            "next_questions": ["치료 중 필요한 생활비는 얼마인가요?"],
            "next_steps": ["유지 가능한 예산을 확인해 보세요."],
        }

    result = analyze_portfolio(
        [policy],
        demographics=InsuredDemographics(age=35, gender="여성", source="user"),
        complete=complete,
    )

    assert result.generation == "llm"
    assert result.counselor.strengths[0].evidence_ids == ["coverage:1"]
    assert result.counselor.amount_review_items[0].current_amount == 30_000_000
    assert result.counselor.amount_review_items[0].confidence == "low"
    assert result.counselor.amount_review_items[0].suggested_range is None


def test_analysis_filters_hallucinated_evidence_and_risky_claims() -> None:
    policy = _policy("p1", "질병", "암진단비", "3,000만원")

    def complete(_: str, __: str) -> dict[str, object]:
        return {
            "strengths": [
                {
                    "title": "치매 진단 담보가 확인돼요",
                    "detail": "가입 사실을 확인했습니다.",
                    "evidence_ids": ["coverage:999"],
                },
                {
                    "title": "보험금이 지급됩니다",
                    "detail": "현재 증권에서 확인했습니다.",
                    "evidence_ids": ["coverage:1"],
                },
            ],
            "gaps": [],
            "amount_review_items": [],
            "next_questions": ["반드시 가입하세요"],
            "next_steps": [],
        }

    result = analyze_portfolio([policy], age=35, gender="여성", complete=complete)

    assert result.generation == "fallback"
    assert "치매" not in result.model_dump_json()
    assert "보험금이 지급됩니다" not in result.model_dump_json()


def test_analysis_uses_deterministic_fallback_when_completer_fails() -> None:
    def fail(_: str, __: str) -> dict[str, object]:
        raise RuntimeError("offline")

    result = analyze_portfolio(
        [_policy("p1", "질병", "암진단비", "3,000만원")],
        age=35,
        gender="여성",
        complete=fail,
    )

    assert result.generation == "fallback"
    assert result.counselor.amount_review_items[0].suggested_range is None
    assert any("AI 분석" in limitation for limitation in result.limitations)


def test_analysis_excludes_auto_policy_from_consultation_facts() -> None:
    result = analyze_portfolio(
        [_policy("car", "자동차보험", "상해사망", "1억원")],
        age=35,
        gender="남성",
    )

    assert result.status == "empty"
    assert result.policy_count == 0
    assert result.excluded_auto_policy_count == 1
    assert result.sources == []


def test_analysis_compares_held_coverages_with_life_stage_checklist() -> None:
    policies = [
        _policy("p1", "질병", "암진단비", "3,000만원"),
        _policy("p2", "실손", "실손의료비", "5,000만원"),
    ]

    result = analyze_portfolio(policies, age=35, gender="여성")

    assert result.life_stage == "성인"
    assert result.gender == "여성"
    assert result.prepared_coverages == ["암 진단", "실손의료"]
    assert {gap.category for gap in result.coverage_gaps} == {
        "뇌혈관 진단",
        "심장질환 진단",
        "사망",
        "상해 후유장해",
    }
