"""Agent SDK tools for the plain-free-text qa baseline.

No slot registry, no structured output: each tool returns the same
deterministic facts counsel/facts/ (and, increasingly, portfolio/ and
reference_data/) already compute, and the agent quotes them directly in its
own free-text answer. See agent.py's module docstring for why.

Split into one file per domain (mirrors counsel/facts/'s layout) so
independent tools can be added without one file growing without bound.
"""

from agents import Tool

from app.modules.qa.tools.claims import get_claim_channels
from app.modules.qa.tools.coverages import (
    calculate_coverage_total,
    find_coverages,
    find_overlapping_coverages,
    list_coverage_names,
)
from app.modules.qa.tools.disclosure import get_disclosure_links
from app.modules.qa.tools.policies import list_policies
from app.modules.qa.tools.portfolio import portfolio_overview
from app.modules.qa.tools.rag import retrieve_official_guidance, retrieve_policy_terms
from app.modules.qa.tools.special_policies import special_policy_overview

ALL_TOOLS: list[Tool] = [
    list_policies,
    list_coverage_names,
    find_coverages,
    calculate_coverage_total,
    find_overlapping_coverages,
    get_claim_channels,
    portfolio_overview,
    special_policy_overview,
    get_disclosure_links,
    retrieve_official_guidance,
    retrieve_policy_terms,
]

__all__ = [
    "ALL_TOOLS",
    "calculate_coverage_total",
    "find_coverages",
    "find_overlapping_coverages",
    "get_claim_channels",
    "get_disclosure_links",
    "list_coverage_names",
    "list_policies",
    "portfolio_overview",
    "retrieve_official_guidance",
    "retrieve_policy_terms",
    "special_policy_overview",
]
