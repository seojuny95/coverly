from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import get_settings
from app.core.errors import (
    ApiError,
    api_error_handler,
    api_error_responses,
    http_error_handler,
    request_validation_error_handler,
    unexpected_error_middleware,
)
from app.core.middleware import request_id_middleware
from app.lifespan import lifespan
from app.modules.portfolio.router import router as portfolio_router
from app.modules.portfolio.session.router import router as portfolio_sessions_router
from app.modules.qa.route import router as qa_router
from app.modules.upload.router import router as policies_router


def health() -> dict[str, str]:
    return {"status": "ok"}


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Coverly API", lifespan=lifespan)
    app.middleware("http")(unexpected_error_middleware)
    app.middleware("http")(request_id_middleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.parsed_backend_cors_origins(),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, request_validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_error_handler)
    app.include_router(policies_router)
    app.include_router(portfolio_sessions_router)
    app.include_router(portfolio_router)
    app.include_router(qa_router)
    app.add_api_route(
        "/health",
        health,
        methods=["GET"],
        responses=api_error_responses(),
    )
    return app


app = create_app()
