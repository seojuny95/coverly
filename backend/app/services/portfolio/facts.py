"""Stable portfolio facts shared by analysis and Q&A."""

from dataclasses import dataclass

from app.schemas.portfolio import PolicyInput, PortfolioCoverageSummary
from app.services.portfolio.policy_classification import is_damage_policy
from app.services.portfolio.summary import summarize_portfolio_coverages


@dataclass(frozen=True)
class PortfolioFacts:
    """Deterministic facts reusable by analysis and Q&A without RAG."""

    policies: tuple[PolicyInput, ...]
    coverage_summary: PortfolioCoverageSummary


def build_portfolio_facts(policies: list[PolicyInput]) -> PortfolioFacts:
    """Build the deterministic common input for summary, analysis, and Q&A."""

    return PortfolioFacts(
        policies=tuple(policy for policy in policies if not is_damage_policy(policy)),
        coverage_summary=summarize_portfolio_coverages(policies),
    )
