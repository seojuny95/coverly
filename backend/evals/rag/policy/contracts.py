"""Evidence model the policy RAG evaluation feeds to the generator.

app/rag/policy/generation.py only requires the PolicyEvidence protocol. This
is the concrete shape the evaluation builds, so it lives with the evaluation
rather than in runtime code no caller there uses.
"""

from pydantic import BaseModel, Field


class ConsultationEvidence(BaseModel):
    """A fact that generated consultation copy may cite."""

    id: str
    fact: str
    source_title: str | None = None
    publisher: str | None = None
    citation_label: str | None = None
    policy_id: str | None = None
    insurer: str | None = None
    product_name: str | None = None
    coverage_name: str | None = None
    amount: int | None = Field(default=None, ge=0)
