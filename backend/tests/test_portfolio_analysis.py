from pytest import MonkeyPatch

from app.schemas.analysis import AnalysisContextAnswer
from app.schemas.consultation import InsuredDemographics
from app.schemas.portfolio import PolicyInput
from app.services.analysis import service as portfolio_analysis
from app.services.analysis.generation import _system_prompt
from app.services.analysis.service import analyze_portfolio
from app.services.rag.official.models import RagChunk, RetrievalHit


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


def _official_hit(text: str) -> RetrievalHit:
    return RetrievalHit(
        chunk=RagChunk(
            id="official-analysis-1",
            source_id="standard_terms_annex_15_2026_06_30",
            source_title="표준약관",
            source_category="standard_clause",
            publisher="금융감독원",
            text=text,
            page_start=10,
            page_end=10,
            citation_label="표준약관 제3조",
        ),
        score=1.0,
        keyword_score=1.0,
        vector_score=1.0,
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


def test_analysis_recognizes_indemnity_from_payment_type() -> None:
    policy = PolicyInput.model_validate(
        {
            "id": "p1",
            "기본정보": {"보험분류": "질병"},
            "보장목록": [
                {
                    "담보명": "질병입원의료비",
                    "가입금액": "5,000만원",
                    "지급유형": "실손",
                }
            ],
        }
    )

    result = analyze_portfolio([policy], age=35, gender="여성")

    assert "실손의료" in result.prepared_coverages
    assert all(gap.category != "실손의료" for gap in result.coverage_gaps)


def test_analysis_accepts_only_cited_llm_insights_and_ignores_amount_review() -> None:
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
    assert result.counselor.amount_review_items == []


def test_analysis_passes_official_guidance_without_changing_evidence_judgment(
    monkeypatch: MonkeyPatch,
) -> None:
    policy = _policy("p1", "질병", "암진단비", "3,000만원")

    monkeypatch.setattr(
        portfolio_analysis,
        "_official_analysis_guidance",
        lambda: (_official_hit("약관에서 지급사유, 면책, 감액 조건을 확인해야 합니다."),),
    )

    def complete(_: str, user: str) -> dict[str, object]:
        assert "official_guidance" in user
        assert '"id":"official:1"' in user
        assert '"evidence_id":"official:1"' in user
        assert "official-analysis-1" not in user
        assert "지급사유" in user
        return {
            "strengths": [
                {
                    "title": "암 진단 담보가 확인돼요",
                    "detail": "공식 기준상 지급사유와 면책 조건 확인이 필요해요.",
                    "evidence_ids": ["coverage:1", "official:1"],
                }
            ],
            "gaps": [],
            "amount_review_items": [],
            "next_questions": ["지급사유와 면책 조건을 약관에서 확인했나요?"],
            "next_steps": ["약관의 지급사유, 면책, 감액 조건을 함께 확인해 보세요."],
        }

    result = analyze_portfolio([policy], age=35, gender="여성", complete=complete)

    assert result.generation == "llm"
    assert result.counselor.strengths[0].evidence_ids == ["coverage:1", "official:1"]
    assert result.evidence[-1].id == "official:1"
    assert result.evidence[-1].source_title == "표준약관"
    assert result.evidence[-1].publisher == "금융감독원"
    assert result.evidence[-1].citation_label == "표준약관 제3조"
    assert len(result.evidence[-1].fact) < 800
    assert result.counselor.next_steps == ["약관의 지급사유, 면책, 감액 조건을 함께 확인해 보세요."]


def test_analysis_rejects_official_guidance_as_standalone_user_coverage_evidence(
    monkeypatch: MonkeyPatch,
) -> None:
    policy = _policy("p1", "질병", "암진단비", "3,000만원")

    monkeypatch.setattr(
        portfolio_analysis,
        "_official_analysis_guidance",
        lambda: (_official_hit("약관에서 지급사유, 면책, 감액 조건을 확인해야 합니다."),),
    )

    def complete(_: str, __: str) -> dict[str, object]:
        return {
            "strengths": [
                {
                    "title": "공식자료 기준 점검",
                    "detail": "공식 기준상 지급사유와 면책 조건 확인이 필요해요.",
                    "evidence_ids": ["official:1"],
                }
            ],
            "gaps": [],
            "amount_review_items": [],
            "next_questions": [],
            "next_steps": ["약관의 지급사유, 면책, 감액 조건을 함께 확인해 보세요."],
        }

    result = analyze_portfolio([policy], age=35, gender="여성", complete=complete)

    assert result.generation == "llm"
    assert result.counselor.strengths[0].evidence_ids == ["coverage:1"]
    assert result.counselor.next_steps == ["약관의 지급사유, 면책, 감액 조건을 함께 확인해 보세요."]


def test_analysis_rejects_personal_adequacy_claim_even_with_official_evidence(
    monkeypatch: MonkeyPatch,
) -> None:
    policy = _policy("p1", "질병", "암진단비", "3,000만원")

    monkeypatch.setattr(
        portfolio_analysis,
        "_official_analysis_guidance",
        lambda: (_official_hit("약관에서 지급사유와 면책 조건을 확인해야 합니다."),),
    )

    def complete(_: str, __: str) -> dict[str, object]:
        return {
            "strengths": [
                {
                    "title": "암 진단 담보가 확인돼요",
                    "detail": "공식 기준상 현재 가입금액은 충분합니다.",
                    "evidence_ids": ["coverage:1", "official:1"],
                }
            ],
            "gaps": [],
            "amount_review_items": [],
            "next_questions": [],
            "next_steps": [],
        }

    result = analyze_portfolio([policy], age=35, gender="여성", complete=complete)

    assert result.generation == "llm"
    assert "공식 기준상" not in result.counselor.strengths[0].detail
    assert "충분합니다" not in result.counselor.strengths[0].detail
    assert result.counselor.strengths[0].evidence_ids == ["coverage:1", "official:1"]


def test_analysis_does_not_auto_attach_official_evidence_from_keywords(
    monkeypatch: MonkeyPatch,
) -> None:
    policy = _policy("p1", "실손", "실손의료비", "5,000만원")

    monkeypatch.setattr(
        portfolio_analysis,
        "_official_analysis_guidance",
        lambda: (_official_hit("약관상 보상하지 않는 사항과 자기부담금을 확인해야 합니다."),),
    )

    def complete(_: str, __: str) -> dict[str, object]:
        return {
            "strengths": [
                {
                    "title": "실손의료비 담보가 확인돼요",
                    "detail": "치료비 부담을 약관상 한도와 자기부담금에 따라 보전하는 성격이에요.",
                    "evidence_ids": ["coverage:1"],
                }
            ],
            "gaps": [],
            "amount_review_items": [],
            "next_questions": [],
            "next_steps": [],
        }

    result = analyze_portfolio([policy], age=35, gender="여성", complete=complete)

    assert result.generation == "llm"
    assert result.counselor.strengths[0].evidence_ids == ["coverage:1"]


def test_analysis_keeps_useful_questions_and_steps_without_sales_language() -> None:
    policy = _policy("p1", "질병", "암진단비", "3,000만원")

    def complete(_: str, __: str) -> dict[str, object]:
        return {
            "strengths": [],
            "gaps": [],
            "amount_review_items": [],
            "next_questions": [
                "현재 보험료를 계속 유지할 수 있는 월 예산은 얼마인가요?",
            ],
            "next_steps": [
                "현재 금액이 생활비를 얼마나 준비할 수 있는지 비교해보면 좋아요.",
                "암보험 추가 가입을 고려해 보세요.",
                "추가적인 보장 항목을 확인하는 것이 좋습니다.",
                "필요한 보장 항목을 점검해보세요.",
            ],
        }

    result = analyze_portfolio([policy], age=35, gender="여성", complete=complete)

    assert result.generation == "llm"
    assert result.counselor.next_questions == [
        "현재 보험료를 계속 유지할 수 있는 월 예산은 얼마인가요?"
    ]
    assert result.counselor.next_steps == [
        "현재 금액이 생활비를 얼마나 준비할 수 있는지 비교해보면 좋아요."
    ]


def test_analysis_passes_user_answers_as_personal_context() -> None:
    policy = _policy("p1", "질병", "암진단비", "3,000만원")

    def complete(_: str, user: str) -> dict[str, object]:
        assert '"personal_context"' in user
        assert '"question":"치료 중 필요한 생활비는 얼마인가요?"' in user
        assert '"answer":"매달 250만원 정도예요."' in user
        return {
            "overview": "사용자가 알려준 월 생활비와 현재 가입금액을 함께 살펴봤어요.",
            "strengths": [],
            "gaps": [],
            "amount_review_items": [{"coverage_evidence_id": "coverage:1"}],
            "next_questions": [
                "치료 기간의 월 생활비는 얼마인가요?",
                "보험료로 유지 가능한 예산은 얼마인가요?",
            ],
            "next_steps": ["현재 가입금액을 생활비와 비교해 보세요."],
        }

    result = analyze_portfolio(
        [policy],
        age=35,
        gender="여성",
        complete=complete,
        personal_context=(
            AnalysisContextAnswer(
                question="치료 중 필요한 생활비는 얼마인가요?",
                answer="매달 250만원 정도예요.",
            ),
        ),
    )

    assert result.generation == "llm"
    assert "월 생활비" in result.counselor.overview
    assert result.counselor.next_questions == ["보험료로 유지 가능한 예산은 얼마인가요?"]
    assert result.counselor.amount_review_items == []


def test_analysis_removes_answered_topics_from_fallback_questions() -> None:
    policy = _policy("p1", "질병", "암진단비", "3,000만원")

    def complete(_: str, __: str) -> dict[str, object]:
        return {
            "overview": "확인된 가입금액과 개인 맥락을 함께 살펴봤어요.",
            "strengths": [],
            "gaps": [],
            "amount_review_items": [{"coverage_evidence_id": "coverage:1"}],
            "next_questions": ["치료 중 필요한 생활비는 얼마인가요?"],
            "next_steps": [],
        }

    result = analyze_portfolio(
        [policy],
        age=35,
        gender="여성",
        complete=complete,
        personal_context=(
            AnalysisContextAnswer(
                question="치료 중 필요한 생활비는 얼마인가요?",
                answer="매달 250만원 정도예요.",
            ),
        ),
    )

    assert "치료 중 필요한 생활비는 얼마인가요?" not in result.counselor.next_questions
    assert result.counselor.next_questions


def test_analysis_keeps_safe_overview_sentences_when_one_is_sales_language() -> None:
    policy = _policy("p1", "질병", "암진단비", "3,000만원")

    def complete(_: str, __: str) -> dict[str, object]:
        return {
            "overview": (
                "암 진단비 담보가 확인됐어요. "
                "다른 증권에 있는 담보도 이어서 확인할 수 있어요. "
                "추가적인 보장 항목을 확인하는 것이 좋습니다."
            ),
            "strengths": [],
            "gaps": [],
            "amount_review_items": [{"coverage_evidence_id": "coverage:1"}],
            "next_questions": [],
            "next_steps": ["다른 증권의 담보도 확인해 보세요."],
        }

    result = analyze_portfolio([policy], age=35, gender="여성", complete=complete)

    assert result.counselor.overview == (
        "암 진단비 담보가 확인됐어요. 다른 증권에 있는 담보도 이어서 확인할 수 있어요."
    )
    assert "추가적인 보장" not in result.counselor.overview


def test_analysis_completes_short_overview_with_portfolio_scope() -> None:
    policies = [
        _policy("p1", "질병", "암진단비", "3,000만원"),
        _policy("p2", "질병", "뇌혈관질환진단비", "1,000만원"),
    ]

    def complete(_: str, __: str) -> dict[str, object]:
        return {
            "overview": "진단비 담보를 확인했어요.",
            "strengths": [],
            "gaps": [],
            "next_questions": [],
            "next_steps": ["원본 증권의 세부 조건을 확인해 보세요."],
        }

    result = analyze_portfolio(policies, age=35, gender="여성", complete=complete)

    assert result.counselor.overview.startswith("보험사별로 흩어진 같은 성격의 담보는 하나로 합쳐")


def test_analysis_prompt_allows_grounded_official_guidance_without_inventing_it() -> None:
    prompt = _system_prompt()

    assert "# 역할" in prompt
    assert "# 제품 목적" in prompt
    assert "# evidence 사용 규칙" in prompt
    assert "# 작업 순서" in prompt
    assert "# amount_review_items 작성 규칙" not in prompt
    assert "# overview 작성 규칙" in prompt
    assert "보험 분석가" in prompt
    assert "official_guidance와 official: evidence는 공식자료에서 검색된 보조 근거" in prompt
    assert "제도 설명, 통계가 들어 있으면" in prompt
    assert "그 근거 범위 안에서 설명할 수 있습니다" in prompt
    assert "official_guidance에 없는 공식 기준·통계·수치를 새로 만들지 마세요" in prompt
    assert "official: evidence만 단독으로 strengths/gaps를 만들지 않습니다" in prompt
    assert "관련 official: evidence id도 함께 인용합니다" in prompt
    assert '예: ["indemnity:1", "official:1"]' in prompt
    assert "공식자료 내용이 항목 설명에 직접 쓰이지 않으면" in prompt
    assert "공식자료, 증권, 계산 근거가 있을 때" in prompt
    assert "overview는 3~5문장으로 작성합니다" in prompt
    assert "여러 보험사와 여러 증권에 흩어진 보장을 하나의 포트폴리오로" in prompt
    assert "모든 증권을 함께 봤을 때 새롭게 알 수 있는 사실" in prompt
    assert "strengths/gaps의 제목과 detail을 그대로 다시 나열하거나 복사하지 않습니다" in prompt
    assert "detail은 2문장으로 씁니다" in prompt
    assert "어떤 비용·생활 변화와 관련돼 있어 확인할 가치가 있는지" in prompt
    assert "너무 짧은 한 문장으로 끝내지 않습니다" in prompt
    assert "서로 다른 문장 구조로 씁니다" in prompt
    assert '"대응하는 성격이에요" 같은 같은 어미와 표현을 반복하지 않습니다' in prompt
    assert "category_purposes 문장을 그대로 복사하지 말고" in prompt
    assert "가입 필요로 읽히는 표현을 쓰지 않습니다" in prompt
    assert '"추가적인 보장", "추가 보장 항목", "보장 항목을 더 준비"' in prompt
    assert "다른 증권 확인이나 개인 맥락 확인으로 마무리합니다" in prompt
    assert "기준·통계·제도·지급 구조를 설명할 수 있습니다" in prompt
    assert "근거가 없을 때만" in prompt
    assert "개인별 적정 가입금액, 실제 보험금 지급 가능성" in prompt
    assert "만들거나 단정하지 않습니다" in prompt
    assert "치료비 부담을 약관상 조건에 따라 보전하는 성격" in prompt
    assert '"돌려받아", "보장받을 수 있습니다", "보상받을 수 있습니다"' in prompt
    assert "약관상 조건, 한도," in prompt
    assert "자기부담금에 따라 보전하는 성격" in prompt
    assert "특정 상품의 추가 가입을 고려하라고 말하지 않습니다" in prompt


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

    assert result.generation == "llm"
    assert "치매" not in result.model_dump_json()
    assert "보험금이 지급됩니다" not in result.model_dump_json()
    assert [item.model_dump(mode="json") for item in result.counselor.strengths] == [
        {
            "title": "암진단비 담보가 확인돼요",
            "detail": "현재 증권에서 확인했습니다.",
            "evidence_ids": ["coverage:1"],
        }
    ]


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
    assert result.counselor.amount_review_items == []
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


def test_analysis_reports_indemnity_duplicate_count() -> None:
    def _indemnity(policy_id: str, insurer: str) -> PolicyInput:
        return PolicyInput.model_validate(
            {
                "id": policy_id,
                "기본정보": {"보험사": insurer, "상품명": f"상품-{policy_id}", "보험분류": "실손"},
                "보장목록": [{"담보명": "실손의료비", "지급유형": "실손"}],
            }
        )

    result = analyze_portfolio(
        [_indemnity("p1", "보험사A"), _indemnity("p2", "보험사B")], age=35, gender="여성"
    )

    assert result.indemnity_duplicate_count == 1


def test_analysis_exposes_excluded_coverage_ledger_with_reasons() -> None:
    partial = PolicyInput.model_validate(
        {
            "id": "p1",
            "기본정보": {"보험사": "테스트보험", "상품명": "상품-p1", "보험분류": "질병"},
            "보장목록": [{"담보명": "알 수 없는 담보", "가입금액": "별도 약정"}],
        }
    )

    result = analyze_portfolio([partial], age=35, gender="여성")

    assert result.excluded_coverage_count == len(result.excluded_coverages)
    assert result.excluded_coverages[0].coverage_name == "알 수 없는 담보"
    assert result.excluded_coverages[0].reason


def test_analysis_reports_monthly_premium_total() -> None:
    policy = PolicyInput.model_validate(
        {
            "id": "p1",
            "기본정보": {
                "보험사": "테스트보험",
                "상품명": "상품-p1",
                "보험분류": "질병",
                "보험료": {"금액": 30000, "납입주기": "월납"},
            },
            "보장목록": [{"담보명": "암진단비", "가입금액": "3,000만원", "지급유형": "정액"}],
        }
    )

    result = analyze_portfolio([policy], age=35, gender="여성")

    assert result.premium.monthly_total == 30000
    assert result.premium.monthly_policy_count == 1


def test_fallback_gaps_explain_why() -> None:
    def _boom(*_: object) -> dict[str, object]:
        raise RuntimeError("force fallback")

    held = _policy("p1", "질병", "암진단비", "3,000만원")
    result = analyze_portfolio([held], age=35, gender="여성", complete=_boom)

    # A single-coverage policy leaves most life-stage essentials missing, so gaps
    # are non-empty and every missing category has a purpose sentence.
    assert result.generation == "fallback"
    gap_details = " ".join(item.detail for item in result.counselor.gaps)
    assert "확인되지 않았어요" in gap_details
    assert any(term in gap_details for term in ("점검", "참고", "핵심", "항목"))
