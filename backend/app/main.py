from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.errors import ApiError, api_error_handler
from app.core.lifespan import lifespan
from app.core.middleware import request_id_middleware
from app.modules.policy.router import router as policies_router
from app.modules.portfolio.router import router as portfolio_router
from app.modules.qa.router import router as qa_router


def health() -> dict[str, str]:
    return {"status": "ok"}


def create_app() -> FastAPI:
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
    app.include_router(qa_router)
    app.add_api_route("/health", health, methods=["GET"])
    return app


app = create_app()
