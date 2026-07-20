"""Build the agent's input for one turn, including facts already resolved."""

_CONFIRMED_HEADER = "확인된 사실(도구를 다시 부르지 말고 그대로 쓰세요):"
_ALREADY_SHOWN = "위 내용은 이미 사용자에게 그대로 보여줬습니다. 반복하지 말고 이어서 답하세요."
_HEDGE = (
    "사용자가 말한 이름과 정확히 일치하는 담보가 없어, 어느 담보가 해당하는지는 "
    "해석이 필요합니다. 계약 약관의 정의에 따라 달라질 수 있으니 금액을 확정해서 "
    "말하지 말고, 확인이 필요한 부분을 함께 알려주세요."
)


def build_agent_input(
    question: str,
    *,
    facts: str | None,
    facts_shown: bool,
    needs_hedge: bool,
) -> str:
    """Compose the agent input so it starts from what has already been resolved."""

    if facts is None and not needs_hedge:
        return question

    sections = [f"질문: {question}"]
    if facts is not None:
        sections.append(f"{_CONFIRMED_HEADER}\n{facts}")
    if facts_shown:
        sections.append(_ALREADY_SHOWN)
    if needs_hedge:
        sections.append(_HEDGE)
    return "\n\n".join(sections)
