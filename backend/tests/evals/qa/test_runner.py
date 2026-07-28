from evals.qa.runner import _execution_failure_results


def test_execution_failure_counts_the_failed_and_remaining_turns() -> None:
    case = {
        "id": "multi-turn",
        "intent": "execution failure accounting",
        "turns": [
            {"question": "첫 질문"},
            {"question": "두 번째 질문"},
            {"question": "세 번째 질문"},
        ],
    }

    results = _execution_failure_results(
        case=case,
        failed_turn_index=2,
        elapsed_seconds=1.25,
        error=TimeoutError(),
    )

    assert [result.turn_index for result in results] == [2, 3]
    assert all(result.passed is False for result in results)
    assert all(result.execution_error == "TimeoutError" for result in results)
    assert results[0].elapsed_seconds == 1.25
    assert results[1].elapsed_seconds == 0.0
