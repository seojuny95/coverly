"""Application composition lifecycle for shared resources."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.integrations.openai import configure_agent_sdk_credentials
from app.modules.portfolio.session.service import shared_portfolio_session_service
from app.modules.reference_data.premium_benchmark import warm_premium_benchmark_cache


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_agent_sdk_credentials()
    warm_premium_benchmark_cache()
    try:
        yield
    finally:
        if shared_portfolio_session_service.cache_info().currsize:
            shared_portfolio_session_service().close()
            shared_portfolio_session_service.cache_clear()
