from evals.qa.runner import evaluate, fixture_policies, load_cases


def test_qa_eval_dataset_has_beginner_and_product_scenarios() -> None:
    cases = load_cases()

    assert len(cases) >= 20
    assert {case.profile for case in cases} >= {
        "portfolio_fact",
        "consultation",
        "term",
        "policy_terms",
        "fresh_information",
    }


def test_qa_baseline_eval_runs_without_live_model() -> None:
    cases = load_cases()
    selected = tuple(
        case
        for case in cases
        if case.id in {"portfolio_count", "cancer_total", "duplicate_fixed_coverages"}
    )

    report = evaluate(selected)

    assert report.total == 3
    assert all(result.status != "error" for result in report.results)


def test_qa_eval_fixture_policies_are_loaded_from_json() -> None:
    policies = fixture_policies()

    assert len(policies) == 5
    assert {policy.id for policy in policies} == {
        "health-nh",
        "health-heungkuk",
        "auto-hyundai",
        "medical-samsung",
        "driver-db",
    }
