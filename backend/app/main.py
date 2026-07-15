from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.errors import ApiError, api_error_handler, request_id_middleware
from app.routes.analysis import router as analysis_router
from app.routes.policies import router as policies_router
from app.routes.portfolio import router as portfolio_router
from app.routes.qa import router as qa_router
from app.services.reference.policy_change import warm_policy_change_cache
from app.services.reference.premium_benchmark import warm_premium_benchmark_cache


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    warm_premium_benchmark_cache()
    warm_policy_change_cache()
    yield


app = FastAPI(title="Coverly API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.middleware("http")(request_id_middleware)
app.add_exception_handler(ApiError, api_error_handler)
app.include_router(policies_router)
app.include_router(portfolio_router)
app.include_router(analysis_router)
app.include_router(qa_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
