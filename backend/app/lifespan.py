"""Application composition lifecycle for shared resources."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.integrations.openai import configure_agent_sdk_credentials
from app.modules.portfolio.session.service import shared_portfolio_session_service
from app.modules.reference_data.premium_benchmark import warm_premium_benchmark_cache
from app.observability.agent_tracing import configure_agent_tracing, shutdown_agent_tracing


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_agent_sdk_credentials()
    agent_trace_processor = configure_agent_tracing()
    warm_premium_benchmark_cache()
    try:
        yield
    finally:
        shutdown_agent_tracing(agent_trace_processor)
        if shared_portfolio_session_service.cache_info().currsize:
            shared_portfolio_session_service().close()
            shared_portfolio_session_service.cache_clear()
