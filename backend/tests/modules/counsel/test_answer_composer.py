from app.modules.counsel.answer.composer import compose_fact_answer
from app.modules.counsel.answer.executor import execute_fact_tasks
from app.modules.counsel.planner import CounselPlan, CounselTask
from app.modules.portfolio.schemas import PolicyInput


def _plan(*tasks: CounselTask) -> CounselPlan:
    return CounselPlan(
        rewritten_question="질문",
        in_scope=True,
        reason="보험 질문",
        response_mode="fact_only",
        tasks=list(tasks),
    )


def _policies_with_one_coverage() -> list[PolicyInput]:
    return [
        PolicyInput.model_validate(
            {
                "id": "p1",
                "기본정보": {"보험사": "테스트보험사", "상품명": "테스트상품"},
                "보장목록": [
                    {
                        "담보명": "암진단비(유사암제외)",
                        "가입금액": "2,000만원",
                        "가입금액숫자": 20_000_000,
                        "지급유형": "정액",
                    },
                ],
            }
        ),
    ]


def _policies_without_coverages() -> list[PolicyInput]:
    return [
        PolicyInput.model_validate(
            {"id": "p1", "기본정보": {"보험사": "테스트보험사"}, "보장목록": []}
        ),
    ]


def test_coverage_total_without_requested_names_does_not_claim_a_total() -> None:
    # The planner can emit coverage_total with no coverage names. Rendering that as
    # "합계는 0원이에요" states a confident fact the data does not support — the truth
    # is that we do not know what to add up.
    plan = _plan(CounselTask(kind="coverage_total", coverage_names=[]))

    answer = compose_fact_answer(execute_fact_tasks(plan, _policies_with_one_coverage()))

    assert answer is not None
    assert "0원" not in answer


def test_coverage_list_says_so_when_no_coverage_is_confirmed() -> None:
    plan = _plan(CounselTask(kind="coverage_list"))

    answer = compose_fact_answer(execute_fact_tasks(plan, _policies_without_coverages()))

    assert answer is not None
    assert answer.strip() != "현재 확인된 담보명은 다음과 같아요."


def _indemnity_policies() -> list[PolicyInput]:
    return [
        PolicyInput.model_validate(
            {
                "id": "p1",
                "기본정보": {"보험사": "삼성화재", "상품명": "실손의료보험"},
                "보장목록": [
                    {"담보명": "실손의료비", "가입금액": "5,000만원", "지급유형": "실손"},
                ],
            }
        ),
    ]


def test_claim_channel_answer_includes_the_medical_indemnity_service() -> None:
    plan = _plan(CounselTask(kind="claim_channel", coverage_names=["실손의료비"]))

    answer = compose_fact_answer(execute_fact_tasks(plan, _indemnity_policies()))

    assert answer is not None
    assert "실손24" in answer
    assert "silson24" in answer


def _two_contract_policies() -> list[PolicyInput]:
    return [
        PolicyInput.model_validate(
            {
                "id": "p1",
                "기본정보": {"보험사": "삼성화재", "상품명": "실손의료보험"},
                "보장목록": [{"담보명": "실손의료비", "가입금액": "5,000만원", "지급유형": "실손"}],
            }
        ),
        PolicyInput.model_validate(
            {
                "id": "p2",
                "기본정보": {"보험사": "한화손해보험", "상품명": "한화실손"},
                "보장목록": [{"담보명": "실손의료비", "가입금액": "3,000만원", "지급유형": "실손"}],
            }
        ),
    ]


def test_overlap_answer_names_the_contracts_instead_of_counting_rows() -> None:
    # "실손의료비: 2건" leaves the user to work out what the two are. Say which
    # contracts they are and what each covers.
    plan = _plan(CounselTask(kind="overlap_check"))

    answer = compose_fact_answer(execute_fact_tasks(plan, _two_contract_policies()))

    assert answer is not None
    assert "삼성화재" in answer
    assert "한화손해보험" in answer
    assert "5,000만원" in answer
    assert "2건" not in answer
