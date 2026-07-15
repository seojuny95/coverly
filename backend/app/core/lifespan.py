"""Startup and shutdown lifecycle for shared application resources."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.modules.reference_data.premium_benchmark import warm_premium_benchmark_cache


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    warm_premium_benchmark_cache()
    yield
