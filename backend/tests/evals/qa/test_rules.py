from app.modules.portfolio.schemas import PolicyInput
from evals.qa.rules import ToolCall, TurnOutcome, check_turn


def _policy(담보명: str, 가입금액: str, 보험사: str = "A화재") -> PolicyInput:
    return PolicyInput.model_validate(
        {
            "id": "p1",
            "기본정보": {"보험사": 보험사, "상품명": "테스트상품"},
            "보장목록": [{"담보명": 담보명, "가입금액": 가입금액, "지급유형": "정액"}],
        }
    )


def _outcome(
    *,
    answer: str,
    policies: list[PolicyInput] | None = None,
    tool_calls: list[ToolCall] | None = None,
    tool_outputs: list[str] | None = None,
) -> TurnOutcome:
    return TurnOutcome(
        answer=answer,
        tool_calls=tool_calls or [],
        tool_outputs=tool_outputs or [],
        policies=policies if policies is not None else [_policy("암진단비", "2,000만원")],
    )


def test_include_any_passes_when_one_token_present() -> None:
    turn = {"include_any": ["2,000만원", "4,000만원"]}
    outcome = _outcome(answer="암진단비는 2,000만원이에요.")

    result = check_turn(turn, outcome)

    assert result.passed


def test_include_any_fails_when_none_present() -> None:
    turn = {"include_any": ["2,000만원"]}
    outcome = _outcome(answer="확인이 필요해요.")

    result = check_turn(turn, outcome)

    assert not result.passed
    assert any("include_any" in f for f in result.failures)


def test_include_all_fails_when_one_token_missing() -> None:
    turn = {"include_all": ["2,000만원", "4,000만원"]}
    outcome = _outcome(answer="암진단비는 2,000만원이에요.")

    result = check_turn(turn, outcome)

    assert not result.passed
    assert any("include_all" in f for f in result.failures)


def test_exclude_fails_when_forbidden_token_present() -> None:
    turn = {"exclude": ["해지하세요"]}
    outcome = _outcome(answer="실손 하나는 해지하세요.", policies=[])

    result = check_turn(turn, outcome)

    assert not result.passed
    assert any("exclude" in f for f in result.failures)


def test_expect_in_scope_false_adds_the_decline_rubric_for_the_judge() -> None:
    turn = {"expect_in_scope": False}
    outcome = _outcome(answer="그건 보험 상담 밖의 이야기예요.", policies=[])

    result = check_turn(turn, outcome)

    assert "out_of_scope_decline" in result.judge_rubrics


def test_expect_source_fails_when_no_insurer_is_named() -> None:
    turn = {"expect_source": True}
    outcome = _outcome(answer="암진단비는 2,000만원이에요.")

    result = check_turn(turn, outcome)

    assert any("expect_source" in f for f in result.failures)


def test_expect_source_passes_when_an_insurer_is_named() -> None:
    turn = {"expect_source": True}
    outcome = _outcome(answer="A화재의 암진단비는 2,000만원이에요.")

    result = check_turn(turn, outcome)

    assert not any("expect_source" in f for f in result.failures)


def test_amount_present_in_raw_policy_data_is_not_flagged() -> None:
    turn: dict[str, object] = {}
    outcome = _outcome(answer="암진단비는 2,000만원이에요.")

    result = check_turn(turn, outcome)

    assert result.passed


def test_amount_absent_from_all_grounding_is_flagged_as_fabricated() -> None:
    turn: dict[str, object] = {}
    outcome = _outcome(answer="암진단비는 9,999만원이에요.")

    result = check_turn(turn, outcome)

    assert not result.passed
    assert any("근거 없는 금액" in f and "9,999만원" in f for f in result.failures)


def test_amount_only_present_in_a_tool_output_is_not_flagged() -> None:
    # A computed total (e.g. calculate_coverage_total's sum) never appears
    # verbatim in the raw per-coverage amounts, so it must be grounded via
    # the tool's own return value instead.
    turn: dict[str, object] = {}
    outcome = _outcome(
        answer="두 담보를 합치면 6,000만원이에요.",
        policies=[_policy("암진단비", "2,000만원"), _policy("암진단비", "4,000만원")],
        tool_outputs=['{"total": "6,000만원"}'],
    )

    result = check_turn(turn, outcome)

    assert result.passed


def test_premium_stored_as_a_bare_integer_grounds_the_formatted_amount() -> None:
    # 기본정보.보험료.금액 is a bare int (42000), never a "42,000원" string --
    # comparing literal strings would flag every correctly formatted premium
    # mention as fabricated.
    policy = PolicyInput.model_validate(
        {
            "id": "p1",
            "기본정보": {"보험사": "A화재", "상품명": "테스트상품", "보험료": {"금액": 42000}},
            "보장목록": [],
        }
    )
    turn: dict[str, object] = {}
    outcome = _outcome(answer="월 보험료는 42,000원이에요.", policies=[policy])

    result = check_turn(turn, outcome)

    assert result.passed


def test_computed_total_serialized_as_a_bare_integer_in_tool_output_grounds_it() -> None:
    # A tool's own JSON serialization of an int total has no 원 suffix at
    # all (e.g. `"total": 60000000`), so it needs its own extraction path.
    turn: dict[str, object] = {}
    outcome = _outcome(
        answer="두 담보를 합치면 60,000,000원이에요.",
        policies=[_policy("암진단비", "2,000만원"), _policy("암진단비", "4,000만원")],
        tool_outputs=['{"total": 60000000}'],
    )

    result = check_turn(turn, outcome)

    assert result.passed


def test_an_amount_written_as_cheonmanwon_is_still_checked() -> None:
    # "5천만원" is ordinary phrasing. If the amount regex cannot see it, the
    # figure is never looked up at all and a fabricated number passes.
    turn: dict[str, object] = {}
    outcome = _outcome(
        answer="암진단비는 5천만원이에요.", policies=[_policy("암진단비", "2,000만원")]
    )

    result = check_turn(turn, outcome)

    assert not result.passed
    assert any("5천만원" in f for f in result.failures)


def test_a_grounded_amount_written_as_cheonmanwon_passes() -> None:
    turn: dict[str, object] = {}
    outcome = _outcome(
        answer="실손의료비는 5천만원이에요.", policies=[_policy("실손의료비", "5,000만원")]
    )

    result = check_turn(turn, outcome)

    assert result.passed


def test_an_unrelated_long_number_in_tool_output_does_not_ground_an_amount() -> None:
    # Ids, counts and timestamps also contain long digit runs. Grounding on
    # any of them would let a fabricated figure through by coincidence.
    turn: dict[str, object] = {}
    outcome = _outcome(
        answer="암진단비는 4,000만원이에요.",
        policies=[_policy("암진단비", "2,000만원")],
        tool_outputs=["chunk_id='doc-40000000' retrieved_at=20240101 count=3"],
    )

    result = check_turn(turn, outcome)

    assert not result.passed
    assert any("4,000만원" in f for f in result.failures)


def test_a_value_with_no_grounding_anywhere_is_still_flagged() -> None:
    # The bare-integer extraction from tool output must not become so
    # permissive that it launders a genuinely invented amount.
    turn: dict[str, object] = {}
    outcome = _outcome(
        answer="암진단비는 1억원이에요.",
        policies=[_policy("암진단비", "2,000만원")],
        tool_outputs=['{"담보명": "암진단비", "가입금액": "2,000만원"}'],
    )

    result = check_turn(turn, outcome)

    assert not result.passed
    assert any("근거 없는 금액" in f for f in result.failures)


def test_pronoun_left_in_a_tool_argument_fails_unconditionally() -> None:
    turn: dict[str, object] = {}
    outcome = _outcome(
        answer="확인해볼게요.",
        policies=[],
        tool_calls=[
            ToolCall(name="find_coverages", arguments='{"coverage_names": ["아까 그 담보"]}')
        ],
    )

    result = check_turn(turn, outcome)

    assert not result.passed
    assert any("find_coverages" in f for f in result.failures)


def test_clean_tool_argument_does_not_fail() -> None:
    turn: dict[str, object] = {}
    outcome = _outcome(
        answer="확인해볼게요.",
        policies=[],
        tool_calls=[
            ToolCall(
                name="find_coverages", arguments='{"coverage_names": ["암진단비(유사암제외)"]}'
            )
        ],
    )

    result = check_turn(turn, outcome)

    assert result.passed


def test_malformed_tool_arguments_do_not_crash_the_check() -> None:
    turn: dict[str, object] = {}
    outcome = _outcome(
        answer="확인해볼게요.",
        policies=[],
        tool_calls=[ToolCall(name="find_coverages", arguments="not json")],
    )

    result = check_turn(turn, outcome)

    assert result.passed
