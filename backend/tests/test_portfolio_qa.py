import json
from datetime import UTC, datetime, timedelta
from threading import Barrier
from typing import Any

from pytest import MonkeyPatch

from app.schemas.consultation import InsuredDemographics
from app.schemas.portfolio import PolicyInput
from app.schemas.qa import ConversationMessage, PortfolioQuestionResponse
from app.services.qa.service import answer_portfolio_question
from app.services.rag.official.answer import RagAnswer, RagCitation
from app.services.rag.policy import PolicyChunk, PolicyRetrievalHit

ADULT_BIRTH = "95" + "0524"
YOUNG_ADULT_BIRTH = "05" + "0524"


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
        "실손 어떻게 청구해?", _named_insurer_policies("삼성화재"), complete=forbidden
    )

    assert result.status == "answered"
    assert result.claim_channels is not None
    assert any(insurer.name == "삼성화재" for insurer in result.claim_channels.insurers)
    assert result.claim_channels.indemnity is not None
    assert result.claim_channels.indemnity.name == "실손24"
    assert any("약관" in limitation for limitation in result.limitations)


def test_qa_claim_channels_include_clickable_links() -> None:
    result = answer_portfolio_question("실손 어떻게 청구해?", _named_insurer_policies("삼성화재"))

    assert result.claim_channels is not None
    insurer = result.claim_channels.insurers[0]
    assert insurer.name == "삼성화재"
    assert any(link.url.startswith("http") for link in insurer.links)
    assert result.claim_channels.indemnity is not None
    assert any(link.url.startswith("http") for link in result.claim_channels.indemnity.links)


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


def test_qa_answers_holdings_with_policy_citation() -> None:
    result = answer_portfolio_question("가입한 보험 목록 알려줘", _policies())

    assert result.status == "answered"
    assert "**증권에서 확인된 사실**" in result.answer
    assert "1건" in result.answer
    assert "- 테스트보험 건강보험(질병)" in result.answer
    assert "건강보험" in result.answer
    assert result.citations[0].policy_id == "p1"


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
    result = answer_portfolio_question("실손 청구 어떻게 해?", _health_plus_auto())

    assert result.claim_channels is not None
    names = [insurer.name for insurer in result.claim_channels.insurers]
    assert "삼성화재" in names
    assert "현대해상" not in names


def test_qa_claim_howto_includes_auto_insurer_for_car_question() -> None:
    result = answer_portfolio_question("자동차 사고 청구 어떻게 해?", _health_plus_auto())

    assert result.claim_channels is not None
    names = [insurer.name for insurer in result.claim_channels.insurers]
    assert "현대해상" in names


def test_qa_claim_howto_detects_indemnity_beyond_exact_실손_type() -> None:
    policies = [
        PolicyInput.model_validate(
            {
                "id": "h1",
                "기본정보": {"보험사": "삼성화재", "상품명": "건강보험", "보험분류": "질병"},
                "보장목록": [{"담보명": "실손의료비", "지급유형": "실손형"}],
            }
        )
    ]

    result = answer_portfolio_question("실손 청구 어떻게 해?", policies)

    assert result.claim_channels is not None
    assert result.claim_channels.indemnity is not None
    assert result.claim_channels.indemnity.name == "실손24"


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
    assert "**증권에서 확인된 사실**" in result.answer
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


def test_qa_fast_amount_path_skips_planner_llm_and_policy_rag(
    monkeypatch: MonkeyPatch,
) -> None:
    from app.services.qa import service as portfolio_qa

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
    from app.services.qa import service as portfolio_qa

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
    from app.services.qa import service as portfolio_qa

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
    from app.services.qa import service as portfolio_qa

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
