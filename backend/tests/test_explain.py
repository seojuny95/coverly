from app.services.explain import explain_coverages


def test_generates_an_explanation_for_a_coverage_name() -> None:
    def fake_complete(system: str, user: str) -> dict[str, object]:
        return {"설명목록": [{"담보명": "가입설명담보", "해설": "이런 상황에 보험금을 드려요."}]}

    explanations, ok = explain_coverages(["가입설명담보"], complete=fake_complete)

    assert ok is True
    assert explanations == {"가입설명담보": "이런 상황에 보험금을 드려요."}


def test_explains_every_requested_name() -> None:
    def fake_complete(system: str, user: str) -> dict[str, object]:
        return {
            "설명목록": [
                {"담보명": "다중설명담보A", "해설": "A 설명이에요."},
                {"담보명": "다중설명담보B", "해설": "B 설명이에요."},
            ]
        }

    explanations, ok = explain_coverages(["다중설명담보A", "다중설명담보B"], complete=fake_complete)

    assert ok is True
    assert explanations == {"다중설명담보A": "A 설명이에요.", "다중설명담보B": "B 설명이에요."}


def test_reports_not_ok_when_the_llm_fails() -> None:
    def failing_complete(system: str, user: str) -> dict[str, object]:
        raise RuntimeError("API down")

    explanations, ok = explain_coverages(["실패담보"], complete=failing_complete)

    assert ok is False  # lets the caller degrade to 분석상태=부분
    assert "실패담보" not in explanations


def test_omits_names_the_llm_cannot_explain() -> None:
    def fake_complete(system: str, user: str) -> dict[str, object]:
        return {"설명목록": []}

    explanations, ok = explain_coverages(["설명불가능담보"], complete=fake_complete)

    assert ok is True
    assert explanations == {}


def test_no_names_yields_no_explanations() -> None:
    def fake_complete(system: str, user: str) -> dict[str, object]:
        return {"설명목록": [{"담보명": "지어낸담보", "해설": "호출되면 안 돼요."}]}

    assert explain_coverages([], complete=fake_complete) == ({}, True)
