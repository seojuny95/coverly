import json
from datetime import UTC, datetime, timedelta
from threading import Barrier
from typing import Any

from pytest import MonkeyPatch, raises

from app.modules.evidence.catalog import is_safe_analysis_text
from app.modules.portfolio.schemas import PolicyInput
from app.modules.qa.agent import (
    AgentCounselorDraft,
    QaAgentDependencies,
    QaAgentUnavailable,
    _agent_input,
    _consultation_evidence,
    _validated_agent_response,
    _web_search_response,
)
from app.modules.qa.context import QaContext, build_qa_context
from app.modules.qa.contracts import InsuredDemographics
from app.modules.qa.schemas import AnswerCitation, ConversationMessage, PortfolioQuestionResponse
from app.modules.qa.service import answer_portfolio_question
from app.modules.qa.web_search import (
    SearchPurpose,
    WebSearchResult,
    _contains_unallowed_url,
    _search_prompt,
    _validated_source_urls,
    sanitize_search_query,
    search_allowed_domains,
)
from app.rag.official.answer import RagAnswer, RagCitation
from app.rag.policy import PolicyChunk, PolicyRetrievalHit

ADULT_BIRTH = "95" + "0524"
YOUNG_ADULT_BIRTH = "05" + "0524"


def test_consultation_safety_rejects_payout_promises_and_sales_nudges() -> None:
    assert not is_safe_analysis_text("암진단비 3천만원이 지급됩니다.")
    assert not is_safe_analysis_text("보장이 강력하니 안심하셔도 좋아요.")
    assert not is_safe_analysis_text("비어 있는 담보는 추가로 고려해보세요.")


def _policies() -> list[PolicyInput]:
    return [
        PolicyInput.model_validate(
            {
                "id": "p1",
                "기본정보": {
                    "보험사": "테스트보험",
                    "상품명": "건강보험",
                    "보험분류": "질병",
                    "피보험자정보": {
                        "나이": 35,
                        "성별": "여성",
                        "생애단계": "성인",
                    },
                },
                "보장목록": [
                    {"담보명": "암진단비", "가입금액": "3,000만원", "지급유형": "정액"},
                    {"담보명": "실손의료비", "가입금액": "5,000만원", "지급유형": "실손"},
                ],
            }
        )
    ]


def _alias_policies() -> list[PolicyInput]:
    rows = [
        ("p1", "보험사A", "허혈성심장질환진단비", 10_000_000),
        ("p2", "보험사B", "허혈성심질환진단비(감액없음)", 20_000_000),
    ]
    return [
        PolicyInput.model_validate(
            {
                "id": policy_id,
                "기본정보": {
                    "보험사": insurer,
                    "상품명": f"건강보험-{policy_id}",
                    "보험분류": "질병",
                },
                "보장목록": [
                    {
                        "담보명": coverage_name,
                        "가입금액숫자": amount,
                        "지급유형": "정액",
                    }
                ],
            }
        )
        for policy_id, insurer, coverage_name, amount in rows
    ]


def _named_insurer_policies(insurer: str) -> list[PolicyInput]:
    return [
        PolicyInput.model_validate(
            {
                "id": "p1",
                "기본정보": {"보험사": insurer, "상품명": "건강보험", "보험분류": "질병"},
                "보장목록": [
                    {"담보명": "암진단비", "가입금액": "3,000만원", "지급유형": "정액"},
                    {"담보명": "실손의료비", "가입금액": "5,000만원", "지급유형": "실손"},
                ],
            }
        )
    ]


def _non_life_cancer_policy() -> list[PolicyInput]:
    return [
        PolicyInput.model_validate(
            {
                "id": "p1",
                "기본정보": {
                    "보험사": "흥국화재",
                    "상품명": "건강보험",
                    "보험분류": "손해보험",
                },
                "보장목록": [
                    {
                        "담보명": "암진단비(유사암제외)",
                        "가입금액": "6,000만원",
                        "지급유형": "정액",
                    }
                ],
            }
        )
    ]


def _cancer_scenario_policies() -> list[PolicyInput]:
    rows = (
        ("p1", "NH농협손해보험", "어린이보험", 20_000_000, 20_000_000),
        ("p2", "흥국화재", "자녀보험", 40_000_000, 10_000_000),
    )
    return [
        PolicyInput.model_validate(
            {
                "id": policy_id,
                "기본정보": {
                    "보험사": insurer,
                    "상품명": product,
                    "보험분류": "제3보험",
                },
                "보장목록": [
                    {
                        "담보명": "암진단비(유사암제외)",
                        "가입금액숫자": cancer_amount,
                        "지급유형": "정액",
                    },
                    {
                        "담보명": "유사암진단비",
                        "가입금액숫자": similar_cancer_amount,
                        "지급유형": "정액",
                    },
                ],
            }
        )
        for policy_id, insurer, product, cancer_amount, similar_cancer_amount in rows
    ]


def _five_classification_policies() -> list[PolicyInput]:
    rows = (
        ("third-1", "보험사A", "어린이보험", "제3보험", "암진단비", "정액"),
        ("third-2", "보험사B", "자녀보험", "제3보험", "골절진단비", "정액"),
        ("damage-1", "보험사C", "운전자보험", "손해보험", "벌금", "실손"),
        ("damage-2", "보험사D", "화재보험", "손해보험", "화재손해", "실손"),
        ("auto-1", "보험사E", "자동차보험", "자동차", "대물배상", "실손"),
    )
    return [
        PolicyInput.model_validate(
            {
                "id": policy_id,
                "기본정보": {
                    "보험사": insurer,
                    "상품명": product,
                    "보험분류": classification,
                },
                "보장목록": [{"담보명": coverage, "지급유형": payment_type}],
            }
        )
        for policy_id, insurer, product, classification, coverage, payment_type in rows
    ]


def _unused_web_search(
    query: str,
    *,
    purpose: SearchPurpose,
    allowed_domains: list[str],
) -> WebSearchResult:
    del query, purpose, allowed_domains
    return WebSearchResult(status="unavailable")


class _AssertingAllPolicyAgent:
    def __init__(self) -> None:
        self.seen_policy_ids: list[str | None] = []

    def run(self, context: QaContext) -> PortfolioQuestionResponse:
        self.seen_policy_ids = [policy.id for policy in context.policies]
        return PortfolioQuestionResponse(
            status="answered",
            answer="모든 증권을 확인했어요.",
            citations=[],
            limitations=[],
            suggestions=[],
        )


def _official_answer(question: str) -> RagAnswer:
    assert question
    return RagAnswer(
        status="answered",
        mode="term_explain",
        answer="계약 전 알릴 의무는 가입 전에 중요한 사항을 알려야 한다는 뜻이에요.",
        citations=(
            RagCitation(
                chunk_id="official-1",
                source_id="standard_terms_annex_15_2026_06_30",
                source_title="보험업감독업무시행세칙 별표15 표준약관",
                source_category="standard_clause",
                publisher="금융감독원",
                citation_label="표준약관 제2조(계약 전 알릴 의무)",
                page_start=10,
                page_end=10,
                version_label="시행일 2026-06-30",
                source_url="https://www.law.go.kr/LSW/flDownload.do?flSeq=166365465",
            ),
        ),
        limitations=("공식자료 발췌문에 근거한 일반 설명입니다.",),
    )


def _official_claim_answer(_: str) -> RagAnswer:
    return RagAnswer(
        status="answered",
        mode="claim_check",
        answer=(
            "표준약관 기준으로 암 진단 확정이라는 지급사유에 해당하면 "
            "보험금이 지급됩니다. 업로드된 증권에서 확인된 암진단비 가입금액은 "
            "구조화된 담보 정보로 별도 확인할 수 있어요.\n\n"
            "최종 지급 여부는 가입한 상품 약관과 보험사 심사로 확정돼요."
        ),
        citations=(
            RagCitation(
                chunk_id="official-claim-1",
                source_id="standard_terms_annex_15_2026_06_30",
                source_title="보험업감독업무시행세칙 별표15 표준약관",
                source_category="standard_clause",
                publisher="금융감독원",
                citation_label="표준약관 제3조(보험금의 지급사유)",
                page_start=12,
                page_end=12,
                version_label="시행일 2026-06-30",
                source_url="https://www.law.go.kr/LSW/flDownload.do?flSeq=166365465",
            ),
        ),
        limitations=("표준약관 기준의 일반 확인 안내입니다.",),
        missing_context=("가입 상품 약관", "진단확정 서류"),
    )


def test_qa_routes_official_terms_to_rag_even_without_uploaded_policies() -> None:
    result = answer_portfolio_question(
        "계약 전 알릴 의무가 뭐야?",
        [],
        official_answer=_official_answer,
    )

    assert result.status == "answered"
    assert result.generation == "llm"
    assert result.citations[0].source_id == "standard_terms_annex_15_2026_06_30"
    assert result.citations[0].source_page == 10
    assert "보험증권을 먼저 업로드" not in result.answer


def test_agent_first_holdings_context_includes_every_policy() -> None:
    agent = _AssertingAllPolicyAgent()
    policies = [
        *_policies(),
        *_non_life_cancer_policy(),
        PolicyInput.model_validate(
            {
                "id": "auto1",
                "기본정보": {
                    "보험사": "자동차보험사",
                    "상품명": "자동차보험",
                    "보험분류": "자동차",
                },
                "보장목록": [{"담보명": "대물배상", "지급유형": "실손"}],
            }
        ),
    ]

    result = answer_portfolio_question(
        "가입한 보험을 전부 확인해줘",
        policies,
        agent_runner=agent,
    )

    assert result.status == "answered"
    assert result.answer == "모든 증권을 확인했어요."
    assert agent.seen_policy_ids == ["p1", "p1", "auto1"]


def test_agent_web_search_domains_are_limited_to_official_and_held_insurer() -> None:
    context = build_qa_context(
        "삼성화재 최신 보험금 청구 안내 찾아줘",
        _named_insurer_policies("삼성화재"),
        None,
        [],
    )

    domains = search_allowed_domains(context, "insurer_guidance")

    assert domains == ["samsungfire.com"]
    assert "law.go.kr" not in domains


def test_agent_web_search_law_update_uses_official_source_domains_only() -> None:
    context = build_qa_context("보험업법 최신 개정 알려줘", [], None, [])

    domains = search_allowed_domains(context, "law_update")

    assert domains == [
        "law.go.kr",
        "fsc.go.kr",
        "korea.kr",
        "molit.go.kr",
    ]
    assert "www.samsungfire.com" not in domains


def test_law_search_prompt_requires_explicit_official_nickname_evidence() -> None:
    prompt = _search_prompt("하준이법이 뭐야?", "law_update")

    assert "공식 페이지 본문에 그 별칭이 직접 등장" in prompt
    assert "관련 없는 법률을 유추하지 마세요" in prompt


def test_web_search_keeps_only_cited_allowed_urls_and_caps_them() -> None:
    response = {
        "output": [
            {
                "content": [
                    {
                        "annotations": [
                            {"type": "url_citation", "url": "https://www.korea.kr/one"},
                            {"type": "url_citation", "url": "https://www.molit.go.kr/two"},
                            {"type": "url_citation", "url": "https://www.law.go.kr/three"},
                            {"type": "url_citation", "url": "https://www.korea.kr/four"},
                            {"type": "url_citation", "url": "https://example.com/rejected"},
                        ]
                    }
                ]
            }
        ],
        "web_search_call": {
            "action": {
                "sources": [
                    {"type": "computer_initialize_state", "url": "https://www.law.go.kr/not-cited"}
                ]
            }
        },
    }

    urls = _validated_source_urls(
        response,
        ["www.korea.kr", "www.molit.go.kr", "www.law.go.kr"],
    )

    assert urls == [
        "https://www.korea.kr/one",
        "https://www.molit.go.kr/two",
        "https://www.law.go.kr/three",
    ]


def test_agent_web_search_query_masks_personal_identifiers() -> None:
    query = sanitize_search_query("010-1234-5678 test@example.com 계약 전 알릴 의무")

    assert "010-1234-5678" not in query
    assert "test@example.com" not in query
    assert "[전화번호]" in query
    assert "[이메일]" in query


def test_agent_web_search_rejects_urls_outside_allowlist() -> None:
    assert _contains_unallowed_url(
        "[공식 안내](https://example.com/insurance)",
        ["www.fsc.go.kr"],
    )
    assert not _contains_unallowed_url(
        "[공식 안내](https://www.fsc.go.kr/insurance)",
        ["www.fsc.go.kr"],
    )


def test_qa_allows_grounded_official_payment_explanation() -> None:
    result = answer_portfolio_question(
        "암 진단비 받을 수 있는지 확인 기준 알려줘",
        _policies(),
        official_answer=_official_claim_answer,
    )

    assert result.status == "answered"
    assert "보험금이 지급됩니다" in result.answer
    assert "최종 지급 여부" in result.answer
    assert result.citations[0].source_id == "standard_terms_annex_15_2026_06_30"


def test_qa_ignores_filtered_official_rag_and_uses_existing_flow() -> None:
    def filtered(_: str) -> RagAnswer:
        return RagAnswer(
            status="filtered",
            mode="term_explain",
            answer="공식 자료 근거 안에서 안전하게 답변하지 못했습니다.",
            citations=(),
            limitations=("답변이 근거를 벗어나면 폐기합니다.",),
        )

    result = answer_portfolio_question(
        "가입한 보험 목록 알려줘",
        _policies(),
        official_answer=filtered,
    )

    assert result.status == "answered"
    assert result.citations[0].policy_id == "p1"


def test_qa_degrades_to_existing_flow_when_official_rag_raises() -> None:
    """Regression test: an official-RAG outage (pgvector/OpenAI down) used to
    propagate as an uncaught exception and fail the whole question, even
    though the portfolio-fact fallback below could have answered it."""

    def broken(_: str) -> RagAnswer:
        raise RuntimeError("DATABASE_URL is required for RAG retrieval")

    result = answer_portfolio_question(
        "가입한 보험 목록 알려줘",
        _policies(),
        official_answer=broken,
    )

    assert result.status == "answered"
    assert result.citations[0].policy_id == "p1"


def test_qa_answers_how_to_claim_with_insurer_channels() -> None:
    def forbidden(_: str, __: str) -> dict[str, object]:
        raise AssertionError("LLM should not be called for claim-channel questions")

    result = answer_portfolio_question(
        "실손의료보험 어떻게 청구해?",
        _named_insurer_policies("삼성화재"),
        complete=forbidden,
    )

    assert result.status == "answered"
    assert result.claim_channels is not None
    assert any(insurer.name == "삼성화재" for insurer in result.claim_channels.insurers)
    assert result.claim_channels.medical_indemnity is not None
    assert result.claim_channels.medical_indemnity.name == "실손24"
    assert any("약관" in limitation for limitation in result.limitations)


def test_qa_treats_silson_insurance_alias_as_medical_indemnity() -> None:
    result = answer_portfolio_question(
        "실손보험 어떻게 청구해?",
        _named_insurer_policies("삼성화재"),
    )

    assert result.claim_channels is not None
    assert result.claim_channels.medical_indemnity is not None
    assert result.claim_channels.medical_indemnity.name == "실손24"


def test_qa_treats_silson_insurance_alias_as_medical_indemnity_lookup() -> None:
    result = answer_portfolio_question("실손보험은?", _policies())

    assert result.status == "answered"
    assert "실손의료보험 관련 담보가 확인돼요" in result.answer
    assert "실손형은 실제 발생한 손해" not in result.answer


def test_qa_claim_channels_include_clickable_links() -> None:
    result = answer_portfolio_question(
        "실손의료보험 어떻게 청구해?", _named_insurer_policies("삼성화재")
    )

    assert result.claim_channels is not None
    insurer = result.claim_channels.insurers[0]
    assert insurer.name == "삼성화재"
    assert any(link.url.startswith("http") for link in insurer.links)
    assert result.claim_channels.medical_indemnity is not None
    assert any(
        link.url.startswith("http") for link in result.claim_channels.medical_indemnity.links
    )


def test_qa_does_not_assume_bare_actual_loss_claim_is_medical() -> None:
    result = answer_portfolio_question("실손 청구 어떻게 해?", _named_insurer_policies("삼성화재"))

    assert result.claim_channels is not None
    assert result.claim_channels.medical_indemnity is None


def test_qa_answers_coverage_question_with_hedge_instead_of_refusing() -> None:
    def complete(_system: str, _user: str) -> dict[str, object]:
        return {
            "confirmed_fact": "암 진단 관련 담보가 확인돼요.",
            "guidance": "정확한 지급 여부는 약관과 보험사에서 확인하는 게 좋아요.",
            "evidence_ids": ["coverage:1"],
            "suggestions": [],
            "limitations": [],
        }

    result = answer_portfolio_question(
        "암이면 실제로 보상 받을 수 있어?",
        _named_insurer_policies("삼성화재"),
        complete=complete,
    )

    assert result.status == "answered"


def test_qa_leads_with_held_cancer_benefit_for_colorectal_cancer_diagnosis() -> None:
    def forbidden_official(_: str) -> RagAnswer:
        raise AssertionError("held diagnosis benefits must be resolved before Official RAG")

    result = answer_portfolio_question(
        "대장암 진단 받았는데 보장 받을 수 있나?",
        _cancer_scenario_policies(),
        official_answer=forbidden_official,
    )

    assert result.status == "answered"
    assert "암진단비(유사암제외)" in result.answer
    assert "60,000,000원" in result.answer
    assert "유사암진단비" not in result.answer
    assert "30,000,000원" not in result.answer
    assert "가입 사실과 가입금액" in result.answer
    assert "실제 지급 여부" in result.answer
    assert {citation.coverage_name for citation in result.citations} == {"암진단비(유사암제외)"}


def test_qa_uses_recent_diagnosis_context_for_claim_follow_up() -> None:
    def forbidden_official(_: str) -> RagAnswer:
        raise AssertionError("follow-up must use the held diagnosis benefit")

    result = answer_portfolio_question(
        "내 보험으로 보장 받을 수 있어?",
        _cancer_scenario_policies(),
        history=[ConversationMessage(role="user", content="대장암 진단을 받았어")],
        official_answer=forbidden_official,
    )

    assert result.status == "answered"
    assert "암진단비(유사암제외)" in result.answer
    assert "60,000,000원" in result.answer
    assert "유사암진단비" not in result.answer
    assert result.claim_channels is not None
    assert any(insurer.name == "흥국화재" for insurer in result.claim_channels.insurers)


def test_qa_answers_holdings_with_policy_citation() -> None:
    result = answer_portfolio_question("가입한 보험 목록 알려줘", _policies())

    assert result.status == "answered"
    assert result.answer.startswith("올려주신 증권을 모두 확인해보니")
    assert "1건" in result.answer
    assert "- 테스트보험 · 건강보험 (질병)" in result.answer
    assert "건강보험" in result.answer
    assert result.citations[0].policy_id == "p1"


def test_qa_holdings_count_all_uploaded_policy_classifications() -> None:
    policies = _five_classification_policies()

    result = answer_portfolio_question("가입한 보험은 몇개야?", policies)

    assert result.status == "answered"
    assert "5건" in result.answer
    for product_name in ("어린이보험", "자녀보험", "운전자보험", "화재보험", "자동차보험"):
        assert product_name in result.answer


def test_agent_cannot_replace_locked_five_policy_answer() -> None:
    policies = _five_classification_policies()
    context = build_qa_context("가입한 보험은 몇개야?", policies, None, [])
    authoritative = answer_portfolio_question(context.question, policies)
    dependencies = QaAgentDependencies(
        context=context,
        complete=None,
        official_answer=None,
        web_search=_unused_web_search,
    )
    dependencies.register("grounded", authoritative)

    result = _validated_agent_response(
        context,
        AgentCounselorDraft(
            selected_result_id="grounded:999",
            answer="업로드된 보험은 3건이에요.",
        ),
        dependencies,
    )

    assert "5건" in result.answer
    assert "3건" not in result.answer
    assert result.citations == authoritative.citations


def test_agent_may_add_only_non_factual_counselor_framing() -> None:
    context = build_qa_context("가입한 보험은 몇개야?", _policies(), None, [])
    authoritative = answer_portfolio_question(context.question, context.policies)
    dependencies = QaAgentDependencies(
        context=context,
        complete=None,
        official_answer=None,
        web_search=_unused_web_search,
    )
    registered = dependencies.register("grounded", authoritative)
    framing = "올려주신 내용을 차근차근 정리해드릴게요."

    result = _validated_agent_response(
        context,
        AgentCounselorDraft(
            selected_result_id=registered.result_id or "",
            answer=f"{framing}\n\n{authoritative.answer}",
        ),
        dependencies,
    )

    assert result.answer.startswith(framing)
    assert authoritative.answer in result.answer


def test_agent_may_rewrite_grounded_answer_as_natural_counselor_prose() -> None:
    context = build_qa_context("가입한 보험은 몇개야?", _policies(), None, [])
    authoritative = answer_portfolio_question(context.question, context.policies)
    dependencies = QaAgentDependencies(
        context=context,
        complete=None,
        official_answer=None,
        web_search=_unused_web_search,
    )
    registered = dependencies.register("grounded", authoritative)

    result = _validated_agent_response(
        context,
        AgentCounselorDraft(
            selected_result_id=registered.result_id or "",
            answer="확인해보니 가입한 보험은 **1건**이고, 건강보험이에요.",
        ),
        dependencies,
    )

    assert result.answer == "확인해보니 가입한 보험은 **1건**이고, 건강보험이에요."
    assert result.citations == authoritative.citations


def test_agent_consultation_uses_only_selected_duplicate_evidence() -> None:
    context = build_qa_context("겹치는 보장이 있는지 봐줄래요?", _alias_policies(), None, [])
    duplicate = next(item for item in context.catalog.items if item.id.startswith("coverage:"))
    assert "지급 성격: 정액형" in duplicate.fact
    assert "2개 증권에서 같은 담보명 확인" in duplicate.fact
    assert "보험사A" in duplicate.fact
    assert "보험사B" in duplicate.fact

    dependencies = QaAgentDependencies(
        context=context,
        complete=None,
        official_answer=None,
        web_search=_unused_web_search,
    )
    response = PortfolioQuestionResponse(
        status="answered",
        answer="질문과 직접 관련된 evidence만 사용하세요.",
        citations=[],
        limitations=[],
    )
    registered = dependencies.register(
        "consultation",
        response,
        evidence=context.catalog.items,
    )

    result = _validated_agent_response(
        context,
        AgentCounselorDraft(
            selected_result_id=registered.result_id or "",
            answer=(
                "두 증권에서 같은 계열의 허혈성심질환진단비가 확인돼요. "
                "정액형 담보라 실제 지급은 각 약관의 조건을 따로 확인해야 해요."
            ),
            evidence_ids=[duplicate.id],
        ),
        dependencies,
    )

    assert result.answer.startswith("두 증권에서")
    assert [citation.evidence_id for citation in result.citations] == [duplicate.id]
    assert "피보험자" not in result.answer


def test_overlap_consultation_exposes_only_duplicate_evidence() -> None:
    context = build_qa_context("겹치는 보장이 있는지 봐줄래요?", _alias_policies(), None, [])

    evidence = _consultation_evidence(context)

    assert len(evidence) == 1
    assert evidence[0].id.startswith("coverage:")
    assert "2개 증권에서 같은 담보명 확인" in evidence[0].fact


def test_overlap_consultation_exposes_explicit_no_overlap_evidence() -> None:
    context = build_qa_context("중복 보장이 있어?", _policies(), None, [])

    evidence = _consultation_evidence(context)

    assert [item.id for item in evidence] == ["portfolio:no-overlap"]


def test_consultation_exposes_only_question_relevant_coverage_category() -> None:
    context = build_qa_context("허혈성심질환 보장을 검토해줘", _alias_policies(), None, [])

    evidence = _consultation_evidence(context)

    assert evidence
    assert all("허혈성심질환" in item.fact for item in evidence)


def test_cancer_diagnosis_consultation_does_not_expose_similar_cancer_by_default() -> None:
    context = build_qa_context(
        "대장암 진단 받았는데 보장 받을 수 있나?",
        _cancer_scenario_policies(),
        None,
        [],
    )

    evidence = _consultation_evidence(context)

    assert evidence
    assert any(item.coverage_name == "암진단비(유사암제외)" for item in evidence)
    assert all(item.coverage_name != "유사암진단비" for item in evidence)


def test_consultation_does_not_expose_portfolio_to_unrelated_fact_question() -> None:
    context = build_qa_context("하준이법이 뭐야?", _policies(), None, [])

    assert _consultation_evidence(context) == ()


def test_agent_consultation_rejects_answer_without_selected_evidence() -> None:
    context = build_qa_context("하준이법이 뭐야?", _policies(), None, [])
    dependencies = QaAgentDependencies(
        context=context,
        complete=None,
        official_answer=None,
        web_search=_unused_web_search,
    )
    response = PortfolioQuestionResponse(
        status="answered",
        answer="질문과 직접 관련된 evidence만 사용하세요.",
        citations=[],
        limitations=[],
    )
    registered = dependencies.register(
        "consultation",
        response,
        evidence=context.catalog.items,
    )

    with raises(QaAgentUnavailable):
        _validated_agent_response(
            context,
            AgentCounselorDraft(
                selected_result_id=registered.result_id or "",
                answer="하준이법은 어린이 보호구역 관련 법이에요.",
                evidence_ids=[],
            ),
            dependencies,
        )


def test_agent_cannot_add_claims_when_web_search_has_no_data() -> None:
    context = build_qa_context("하준이법이 뭐야?", _policies(), None, [])
    dependencies = QaAgentDependencies(
        context=context,
        complete=None,
        official_answer=None,
        web_search=_unused_web_search,
    )
    no_data = _web_search_response(context, WebSearchResult(status="unavailable"))
    registered = dependencies.register("web", no_data)

    result = _validated_agent_response(
        context,
        AgentCounselorDraft(
            selected_result_id=registered.result_id or "",
            answer="하준이법은 어린이 안전을 보호하는 법으로 알려져 있어요.",
        ),
        dependencies,
    )

    assert result.answer == no_data.answer
    assert "알려져" not in result.answer
    assert result.suggestions == []
    assert not any("피보험자" in limitation for limitation in result.limitations)


def test_agent_routes_external_law_question_to_official_web_not_portfolio() -> None:
    context = build_qa_context("하준이법이 뭐야?", _policies(), None, [])

    prompt = _agent_input(context)

    assert "법, 제도, 보험 용어처럼 증권 밖의 사실" in prompt
    assert "search_official_web" in prompt
    assert "자녀" not in prompt


def test_agent_requires_web_tool_for_latest_official_information() -> None:
    context = build_qa_context("요즘 보험업법 최신 개정 알려줘", [], None, [])
    authoritative = PortfolioQuestionResponse(
        status="answered",
        answer="기존 공식 RAG 답변",
        citations=[
            AnswerCitation(
                policy_id=None,
                insurer=None,
                product_name=None,
                source_id="old-source",
            )
        ],
        limitations=[],
    )
    dependencies = QaAgentDependencies(
        context=context,
        complete=None,
        official_answer=None,
        web_search=_unused_web_search,
    )
    registered = dependencies.register("grounded", authoritative)

    result = _validated_agent_response(
        context,
        AgentCounselorDraft(
            selected_result_id=registered.result_id or "",
            answer=authoritative.answer,
        ),
        dependencies,
    )

    assert result.status == "no_data"
    assert result.citations == []
    assert "공식 웹사이트 검색 근거" in result.answer


def _health_plus_auto() -> list[PolicyInput]:
    return [
        PolicyInput.model_validate(
            {
                "id": "h1",
                "기본정보": {"보험사": "삼성화재", "상품명": "건강보험", "보험분류": "질병"},
                "보장목록": [{"담보명": "실손의료비", "지급유형": "실손"}],
            }
        ),
        PolicyInput.model_validate(
            {
                "id": "a1",
                "기본정보": {"보험사": "현대해상", "상품명": "하이카", "보험분류": "자동차"},
                "보장목록": [{"담보명": "대물배상", "지급유형": "실손"}],
            }
        ),
    ]


def test_qa_claim_howto_excludes_auto_insurer_for_non_auto_question() -> None:
    result = answer_portfolio_question("실손의료보험 청구 어떻게 해?", _health_plus_auto())

    assert result.claim_channels is not None
    names = [insurer.name for insurer in result.claim_channels.insurers]
    assert "삼성화재" in names
    assert "현대해상" not in names


def test_qa_claim_howto_includes_auto_insurer_for_car_question() -> None:
    result = answer_portfolio_question("자동차 사고 청구 어떻게 해?", _health_plus_auto())

    assert result.claim_channels is not None
    names = [insurer.name for insurer in result.claim_channels.insurers]
    assert "현대해상" in names
    assert result.claim_channels.medical_indemnity is None


def test_qa_non_medical_claim_does_not_include_medical_indemnity_service() -> None:
    result = answer_portfolio_question("암진단비 청구 서류 알려줘", _policies())

    assert result.claim_channels is not None
    assert result.claim_channels.medical_indemnity is None


def test_qa_claim_howto_detects_medical_indemnity_payment_type_variant() -> None:
    policies = [
        PolicyInput.model_validate(
            {
                "id": "h1",
                "기본정보": {"보험사": "삼성화재", "상품명": "건강보험", "보험분류": "질병"},
                "보장목록": [{"담보명": "실손의료비", "지급유형": "실손형"}],
            }
        )
    ]

    result = answer_portfolio_question("실손의료보험 청구 어떻게 해?", policies)

    assert result.claim_channels is not None
    assert result.claim_channels.medical_indemnity is not None
    assert result.claim_channels.medical_indemnity.name == "실손24"


def test_qa_status_counts_auto_policies() -> None:
    result = answer_portfolio_question("분석 상태 알려줘", [_health_plus_auto()[1]])

    assert result.status == "answered"
    assert "자동차보험 1건" in result.answer


def test_qa_holdings_include_auto_policies() -> None:
    policies = _policies()
    policies.append(
        PolicyInput.model_validate(
            {
                "id": "auto1",
                "기본정보": {"보험사": "현대해상", "상품명": "하이카", "보험분류": "자동차"},
                "보장목록": [{"담보명": "대물배상", "지급유형": "실손"}],
            }
        )
    )

    result = answer_portfolio_question("가입한 보험 목록 알려줘", policies)

    assert result.status == "answered"
    assert "2건" in result.answer
    assert "현대해상" in result.answer
    assert "자동차" in result.answer


def test_qa_uses_confirmed_summary_for_amount_answer() -> None:
    result = answer_portfolio_question("전체 가입금액 합계가 얼마야?", _policies())

    assert result.status == "answered"
    assert "**30,000,000원**" in result.answer
    assert "30,000,000원" in result.answer
    assert "실손형 담보는 가입금액 합계에 포함하지 않았습니다." in result.limitations
    assert result.citations[0].coverage_name == "암진단비"


def test_qa_filters_specific_coverage_amount_and_citations() -> None:
    policies = _policies()
    policies[0].보장목록.append(
        policies[0].보장목록[0].model_copy(update={"담보명": "질병수술비", "가입금액": "100만원"})
    )

    result = answer_portfolio_question("암진단비 가입금액은 얼마야?", policies)

    assert result.status == "answered"
    assert "30,000,000원" in result.answer
    assert "31,000,000원" not in result.answer
    assert {citation.coverage_name for citation in result.citations} == {"암진단비"}


def test_qa_resolves_curated_aliases_to_the_same_coverage_total() -> None:
    for question in (
        "허혈성심장질환진단비는 얼마야?",
        "허혈성심질환진단비(감액없음) 가입금액은 얼마야?",
    ):
        result = answer_portfolio_question(question, _alias_policies())

        assert result.status == "answered"
        assert "허혈성심질환진단비" in result.answer
        assert "30,000,000원" in result.answer
        assert {citation.coverage_name for citation in result.citations} == {"허혈성심질환진단비"}


def test_qa_payment_conditions_require_uploaded_policy_terms() -> None:
    policies = [
        PolicyInput.model_validate(
            {
                "id": "damage-1",
                "기본정보": {
                    "보험사": "테스트손해보험",
                    "상품명": "건강보험",
                    "보험분류": "손해보험",
                },
                "보장목록": [
                    {
                        "담보명": "5대장기이식수술비",
                        "가입금액": "1,000만원",
                        "지급유형": "정액",
                    }
                ],
            }
        )
    ]

    result = answer_portfolio_question("5대장기이식수술비 지급 조건은 뭐야?", policies)

    assert result.status == "no_data"
    assert "약관 원문" in result.answer
    assert "암진단비" not in result.answer
    assert result.citations[0].coverage_name == "5대장기이식수술비"


def test_qa_held_coverage_conditions_use_policy_rag_before_official_rag(
    monkeypatch: MonkeyPatch,
) -> None:
    from app.modules.qa import service as qa_service

    policy = _non_life_cancer_policy()[0]
    policy.문서세션ID = "session-1"
    now = datetime(2026, 1, 1, tzinfo=UTC)
    hit = PolicyRetrievalHit(
        chunk=PolicyChunk(
            id="chunk-1",
            session_id="session-1",
            text="암진단비는 보험기간 중 암으로 진단확정된 경우 보험금을 지급합니다.",
            content_type="text",
            chunk_index=1,
            table_index=None,
            created_at=now,
            expires_at=now + timedelta(hours=1),
        ),
        score=1.0,
    )
    monkeypatch.setattr(qa_service, "retrieve_policy_context", lambda _ids, _query: [hit])

    def forbidden_official(_: str) -> RagAnswer:
        raise AssertionError("held coverage conditions must use uploaded policy terms first")

    result = answer_portfolio_question(
        "암진단비 지급사유는 뭐야?",
        [policy],
        official_answer=forbidden_official,
        complete=lambda _system, _user: {
            "confirmed_fact": "암으로 진단확정된 경우 보험금을 지급합니다.",
            "guidance": None,
            "evidence_ids": ["session:1"],
            "suggestions": [],
            "limitations": [],
        },
    )

    assert result.status == "answered"
    assert result.citations[0].evidence_id == "session:1"
    assert "진단확정된 경우" in result.answer


def test_web_search_response_refuses_results_without_valid_source_url() -> None:
    context = build_qa_context("보험업법 최신 개정 알려줘", [], None, [])

    result = _web_search_response(
        context,
        WebSearchResult(
            status="searched",
            answer="최근 법이 바뀌었습니다.",
            source_urls=[],
        ),
    )

    assert result.status == "no_data"
    assert result.citations == []


def test_web_search_response_keeps_verified_official_source_url() -> None:
    context = build_qa_context("보험업법 최신 개정 알려줘", [], None, [])

    result = _web_search_response(
        context,
        WebSearchResult(
            status="searched",
            answer="공식 사이트에 게시된 최신 내용을 확인했어요.",
            source_urls=["https://www.fsc.go.kr/example"],
        ),
    )

    assert result.status == "answered"
    assert result.citations[0].source_url == "https://www.fsc.go.kr/example"


def test_qa_does_not_fall_back_to_total_for_unknown_specific_coverage() -> None:
    result = answer_portfolio_question("골절진단비는 얼마야?", _policies())

    assert result.status == "no_data"
    assert result.citations == []
    assert "찾지 못" in result.answer


def test_qa_offers_grounded_adequacy_review() -> None:
    review = answer_portfolio_question(
        "이 보험이면 충분해?",
        _policies(),
        demographics=InsuredDemographics(age=35, gender="여성", source="policy"),
        complete=lambda _system, _user: (_ for _ in ()).throw(RuntimeError("offline")),
    )

    assert review.status == "answered"
    assert review.citations
    assert "함께 살펴볼 제안" in review.answer


def test_qa_returns_no_data_without_uploaded_policies() -> None:
    result = answer_portfolio_question("내 보험 목록 알려줘", [])

    assert result.status == "no_data"
    assert result.citations == []


def test_qa_returns_clarify_status_for_ambiguous_planned_reference() -> None:
    result = answer_portfolio_question(
        "그건 얼마야?",
        _policies(),
        plan=lambda _system, _user: {
            "questions": [
                {
                    "original": "그건 얼마야?",
                    "resolved": "대상을 확인해야 하는 가입금액 질문",
                    "scope": "insurance",
                }
            ],
            "clarification": "어떤 담보의 가입금액을 말씀하시는지 알려주세요.",
        },
    )

    assert result.status == "clarify"
    assert "**확인이 필요해요**" in result.answer
    assert "어떤 담보의 가입금액을 말씀하시는지 알려주세요." in result.answer


def test_qa_passes_recent_history_and_demographics_to_llm() -> None:
    captured: dict[str, object] = {}

    def complete(_: str, user: str) -> dict[str, object]:
        captured.update(json.loads(user))
        return {
            "confirmed_fact": "암 진단 관련 담보의 가입 사실이 확인돼요.",
            "guidance": "일반 가이드로 생활비와 예산을 함께 비교해 보세요.",
            "evidence_ids": ["coverage:1"],
            "suggestions": ["수술비도 함께 볼까요?"],
            "limitations": [],
        }

    result = answer_portfolio_question(
        "그럼 무엇을 먼저 볼까?",
        _policies(),
        demographics=InsuredDemographics(age=35, gender="여성", source="policy"),
        history=[ConversationMessage(role="user", content="암 진단비부터 봐줘")],
        complete=complete,
    )

    assert result.generation == "llm"
    assert result.citations[0].evidence_id == "coverage:1"
    assert captured["history"] == [{"role": "user", "content": "암 진단비부터 봐줘"}]
    assert captured["demographics"] == {
        "age": 35,
        "gender": "여성",
        "source": "policy",
        "status": "verified_policy",
    }


def test_qa_masks_identifiers_in_question_and_history_before_llm() -> None:
    captured: dict[str, object] = {}
    question_identifier = f"{ADULT_BIRTH}-1******"
    history_identifier = YOUNG_ADULT_BIRTH + "4123456"

    def complete(_: str, user: str) -> dict[str, object]:
        captured.update(json.loads(user))
        assert question_identifier not in user
        assert history_identifier not in user
        assert ADULT_BIRTH not in user
        assert YOUNG_ADULT_BIRTH not in user
        return {
            "confirmed_fact": "암 진단 관련 담보의 가입 사실이 확인돼요.",
            "guidance": "일반 가이드로 생활비와 예산을 함께 비교해 보세요.",
            "evidence_ids": ["coverage:1"],
            "suggestions": [],
            "limitations": [],
        }

    result = answer_portfolio_question(
        f"제 정보 {question_identifier}를 바탕으로 무엇을 준비할까요?",
        _policies(),
        demographics=InsuredDemographics(age=35, gender="여성", source="policy"),
        history=[
            ConversationMessage(
                role="user",
                content=f"이전 정보는 {history_identifier}였어요.",
            )
        ],
        complete=complete,
    )

    assert result.generation == "llm"
    assert captured["question"] == "제 정보 ******-*******를 바탕으로 무엇을 준비할까요?"
    assert captured["history"] == [{"role": "user", "content": "이전 정보는 ******-*******였어요."}]


def test_qa_filters_hallucinated_numbers_and_invalid_evidence() -> None:
    def complete(_: str, __: str) -> dict[str, object]:
        return {
            "confirmed_fact": "치매진단비 1억원이 가입되어 있어요.",
            "guidance": "충분합니다.",
            "evidence_ids": ["coverage:999"],
            "suggestions": [],
            "limitations": [],
        }

    result = answer_portfolio_question(
        "내 보장의 좋은 점을 알려줘",
        _policies(),
        demographics=InsuredDemographics(age=35, gender="여성", source="policy"),
        complete=complete,
    )

    assert result.generation == "fallback"
    assert "치매진단비" not in result.answer
    assert "1억원" not in result.answer


def test_qa_keeps_guidance_with_everyday_advisory_words() -> None:
    def complete(_: str, __: str) -> dict[str, object]:
        return {
            "confirmed_fact": "암 진단 담보의 가입 사실이 확인돼요.",
            "guidance": "지금 보장을 잘 유지하시면 좋아요. 필요할 때 함께 준비해요.",
            "evidence_ids": ["coverage:1"],
            "suggestions": [],
            "limitations": [],
        }

    result = answer_portfolio_question(
        "내 보장을 어떻게 준비할까?",
        _policies(),
        demographics=InsuredDemographics(age=35, gender="여성", source="policy"),
        complete=complete,
    )

    assert result.generation == "llm"
    assert "유지하시면 좋아요" in result.answer


def test_qa_allows_hedged_money_range_in_guidance() -> None:
    def complete(_: str, __: str) -> dict[str, object]:
        return {
            "confirmed_fact": "암 진단 담보의 가입 사실이 확인돼요.",
            "guidance": "정답은 아니지만 월 3만원 정도로 준비하는 분들도 있어요.",
            "evidence_ids": ["coverage:1"],
            "suggestions": [],
            "limitations": [],
        }

    result = answer_portfolio_question(
        "내 보장을 어떻게 준비할까?",
        _policies(),
        demographics=InsuredDemographics(age=35, gender="여성", source="policy"),
        complete=complete,
    )

    assert result.generation == "llm"
    assert "월 3만원" in result.answer


def test_qa_drops_unsafe_guidance_but_keeps_confirmed_answer() -> None:
    def complete(_: str, __: str) -> dict[str, object]:
        return {
            "confirmed_fact": "암 진단 담보의 가입 사실이 확인돼요.",
            "guidance": "지금 바로 암보험 가입하세요.",
            "evidence_ids": ["coverage:1"],
            "suggestions": [],
            "limitations": [],
        }

    result = answer_portfolio_question(
        "내 보장을 어떻게 준비할까?",
        _policies(),
        demographics=InsuredDemographics(age=35, gender="여성", source="policy"),
        complete=complete,
    )

    assert result.generation == "llm"
    assert result.citations[0].evidence_id == "coverage:1"
    assert "가입하세요" not in result.answer
    assert any(section.basis == "confirmed_fact" for section in result.sections)
    assert all(section.basis != "general_guidance" for section in result.sections)


def test_qa_does_not_call_llm_for_deterministic_amount_questions() -> None:
    def forbidden(_: str, __: str) -> dict[str, object]:
        raise AssertionError("LLM should not be called")

    amount = answer_portfolio_question(
        "암진단비 가입금액은 얼마야?", _policies(), complete=forbidden
    )

    assert amount.status == "answered"
    assert "30,000,000원" in amount.answer


def test_qa_answers_short_lookup_for_non_life_damage_coverage() -> None:
    result = answer_portfolio_question("암진단비는?", _non_life_cancer_policy())

    assert result.status == "answered"
    assert "암진단비(유사암제외)" in result.answer
    assert "6,000만원" in result.answer
    assert {citation.coverage_name for citation in result.citations} == {"암진단비(유사암제외)"}


def test_qa_answers_amount_lookup_for_non_life_damage_coverage() -> None:
    result = answer_portfolio_question("암진단비는 얼마야?", _non_life_cancer_policy())

    assert result.status == "answered"
    assert "6,000만원" in result.answer
    assert "확인 가능한 가입금액을 찾지 못했어요" not in result.answer


def test_qa_answers_broad_actual_loss_lookup_without_assuming_medical_coverage() -> None:
    result = answer_portfolio_question("실손은?", _non_life_cancer_policy())

    assert result.status == "answered"
    assert "실손형 담보를 확인하지 못했어요" in result.answer
    assert "가입을 고려" not in result.answer
    assert "가입하세요" not in result.answer


def test_qa_broad_actual_loss_lookup_keeps_medical_and_auto_domains_separate() -> None:
    context = build_qa_context("실손은?", _health_plus_auto(), None, None)
    auto_coverage_evidence = [
        item for item in context.catalog.items if item.coverage_name == "대물배상"
    ]

    assert len(auto_coverage_evidence) == 1
    assert auto_coverage_evidence[0].id.startswith("damage:")

    result = answer_portfolio_question("실손은?", _health_plus_auto())

    assert result.status == "answered"
    assert "실손의료보험은 그중 의료비 영역" in result.answer
    assert "실손의료비 (실손의료비)" in result.answer
    assert "대물배상 (자동차 손해 실손형)" in result.answer
    assert any(
        citation.coverage_name == "대물배상" and (citation.evidence_id or "").startswith("damage:")
        for citation in result.citations
    )


def test_qa_keeps_same_actual_loss_name_in_different_domains_separate() -> None:
    policies = [
        PolicyInput.model_validate(
            {
                "id": "health",
                "기본정보": {
                    "보험사": "삼성화재",
                    "상품명": "건강보험",
                    "보험분류": "제3보험",
                },
                "보장목록": [{"담보명": "질병입원의료비", "지급유형": "실손"}],
            }
        ),
        PolicyInput.model_validate(
            {
                "id": "travel",
                "기본정보": {
                    "보험사": "현대해상",
                    "상품명": "여행자보험",
                    "보험분류": "손해보험",
                    "상품태그": ["여행자보험"],
                },
                "보장목록": [{"담보명": "질병입원의료비", "지급유형": "실손"}],
            }
        ),
    ]

    result = answer_portfolio_question("실손은?", policies)

    assert "질병입원의료비 (실손의료비)" in result.answer
    assert "질병입원의료비 (여행 의료비 실손형)" in result.answer
    assert "여러 계약에서 확인" not in result.answer


def test_qa_answers_missing_medical_indemnity_for_specific_question() -> None:
    result = answer_portfolio_question("실손의료비는?", _non_life_cancer_policy())

    assert result.status == "answered"
    assert "실손의료보험 담보를 확인하지 못했어요" in result.answer


def test_qa_life_stage_check_reuses_medical_indemnity_classification() -> None:
    policy = PolicyInput.model_validate(
        {
            "기본정보": {
                "보험사": "보험사A",
                "상품명": "건강보험",
                "보험분류": "제3보험",
            },
            "보장목록": [
                {
                    "담보명": "상해입원의료비",
                    "보장분류": "실손형",
                }
            ],
        }
    )

    context = build_qa_context(
        "내 보장을 확인해줘",
        [policy],
        InsuredDemographics(age=35, gender="여성", source="user"),
        None,
    )

    assert "실손의료비" in context.life_stage_check.held
    assert "실손의료비" not in context.life_stage_check.missing


def test_qa_answers_adequacy_question_from_essential_coverage_check() -> None:
    result = answer_portfolio_question(
        "원래 암진단비는 얼마정도 적당해?", _non_life_cancer_policy()
    )

    assert result.status == "answered"
    assert "60,000,000원" in result.answer
    assert "30,000,000원~50,000,000원" in result.answer
    assert any("공식 기준이 아니라" in limitation for limitation in result.limitations)
    assert "확인 가능한 가입금액을 찾지 못했어요" not in result.answer


def test_qa_fast_amount_path_skips_planner_llm_and_policy_rag(
    monkeypatch: MonkeyPatch,
) -> None:
    from app.modules.qa import service as portfolio_qa

    policy = _policies()[0]
    policy.문서세션ID = "session-1"

    def forbidden_json(_: str, __: str) -> dict[str, object]:
        raise AssertionError("LLM should not be called for deterministic amount questions")

    def forbidden_retrieval(_ids: list[str], _query: str) -> list[PolicyRetrievalHit]:
        raise AssertionError("policy RAG should not run for deterministic amount questions")

    monkeypatch.setattr(portfolio_qa, "retrieve_policy_context", forbidden_retrieval)

    result = portfolio_qa.answer_portfolio_question(
        "암진단비 가입금액은 얼마야?",
        [policy],
        complete=forbidden_json,
        plan=forbidden_json,
    )

    assert result.status == "answered"
    assert "30,000,000원" in result.answer


def test_qa_scope_only_plan_skips_portfolio_context(monkeypatch: MonkeyPatch) -> None:
    from app.modules.qa import service as portfolio_qa

    def forbidden_context(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("scope-only plans should not build portfolio context")

    monkeypatch.setattr(portfolio_qa, "_build_qa_context", forbidden_context)

    result = portfolio_qa.answer_portfolio_question(
        "오늘 날씨 알려줘",
        _policies(),
        plan=lambda _system, _user: {
            "questions": [
                {
                    "original": "오늘 날씨 알려줘",
                    "resolved": "오늘 날씨 알려줘",
                    "scope": "out_of_scope",
                }
            ],
            "clarification": None,
        },
    )

    assert result.status == "refused"
    assert "보험과 관련 없는 정보" in result.answer


def test_qa_answers_multiple_insurance_questions_in_parallel(
    monkeypatch: MonkeyPatch,
) -> None:
    from app.modules.qa import service as portfolio_qa

    barrier = Barrier(2, timeout=5)
    seen_questions: list[str] = []

    def fake_answer_context(context: Any, *_args: object) -> PortfolioQuestionResponse:
        question = context.question
        seen_questions.append(question)
        barrier.wait()
        return PortfolioQuestionResponse(
            status="answered",
            answer=f"{question} 답변",
            citations=[],
            limitations=[],
        )

    monkeypatch.setattr(portfolio_qa, "_answer_context", fake_answer_context)

    result = portfolio_qa.answer_portfolio_question(
        "암진단비하고 실손의료비 알려줘",
        _policies(),
        plan=lambda _system, _user: {
            "questions": [
                {
                    "original": "암진단비",
                    "resolved": "암진단비 가입금액은 얼마야?",
                    "scope": "insurance",
                },
                {
                    "original": "실손의료비",
                    "resolved": "실손의료비 가입 여부는 어때?",
                    "scope": "insurance",
                },
            ],
            "clarification": None,
        },
    )

    assert set(seen_questions) == {
        "암진단비 가입금액은 얼마야?",
        "실손의료비 가입 여부는 어때?",
    }
    assert result.answer.split("\n\n") == [
        "**암진단비**",
        "암진단비 가입금액은 얼마야? 답변",
        "**실손의료비**",
        "실손의료비 가입 여부는 어때? 답변",
    ]


def test_qa_adds_session_policy_text_to_llm_context(monkeypatch: MonkeyPatch) -> None:
    from app.modules.qa import service as portfolio_qa

    policy = _policies()[0]
    policy.문서세션ID = "session-1"
    now = datetime(2026, 1, 1, tzinfo=UTC)
    hit = PolicyRetrievalHit(
        chunk=PolicyChunk(
            id="session:session-1:1",
            session_id="session-1",
            text="암진단비 특별약관 원문에 진단확정 문구가 있습니다.",
            content_type="text",
            chunk_index=1,
            table_index=None,
            created_at=now,
            expires_at=now + timedelta(hours=1),
        ),
        score=1.0,
    )
    monkeypatch.setattr(portfolio_qa, "retrieve_policy_context", lambda _ids, _query: [hit])

    def complete(_: str, user: str) -> dict[str, object]:
        assert "session:1" in user
        assert "진단확정" in user
        return {
            "confirmed_fact": "암 진단 담보 원문 발췌를 확인했어요.",
            "guidance": None,
            "evidence_ids": ["session:1"],
            "suggestions": [],
            "limitations": [],
        }

    result = answer_portfolio_question(
        "암진단비 원문에는 뭐라고 적혀 있어?",
        [policy],
        complete=complete,
    )

    assert result.generation == "llm"
    assert result.citations[0].evidence_id == "session:1"
