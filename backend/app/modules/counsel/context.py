"""Local context passed to the counsel agent run."""

from dataclasses import dataclass

from app.modules.portfolio.schemas import PolicyInput


@dataclass(frozen=True)
class CounselContext:
    policies: list[PolicyInput]
