"""Agent tool registry assembled from responsibility-focused tool modules."""

from agents.tool import Tool

from app.modules.qa.tools.claims import get_claim_channels
from app.modules.qa.tools.coverages import (
    calculate_coverage_total,
    find_coverages,
    find_overlapping_coverages,
)
from app.modules.qa.tools.policies import inspect_portfolio, list_policies
from app.modules.qa.tools.rag import retrieve_official_guidance, retrieve_policy_terms
from app.modules.qa.tools.web import search_official_web

QA_AGENT_TOOLS: list[Tool] = [
    list_policies,
    find_coverages,
    inspect_portfolio,
    calculate_coverage_total,
    find_overlapping_coverages,
    get_claim_channels,
    retrieve_official_guidance,
    retrieve_policy_terms,
    search_official_web,
]
