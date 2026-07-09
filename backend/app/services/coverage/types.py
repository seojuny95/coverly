from typing import TypedDict


class Coverage(TypedDict):
    """One coverage (담보) row for the /policies/parse response.

    보장내용 is the policy's own wording (authoritative); 해설 is an LLM-generated
    general explanation, filled only when 보장내용 is absent.
    """

    담보명: str
    가입금액: str
    보장내용: str | None
    해설: str | None
