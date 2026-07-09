from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.errors import ApiError, api_error_handler, request_id_middleware
from app.routes.policies import router as policies_router

app = FastAPI(title="Coverly API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.middleware("http")(request_id_middleware)
app.add_exception_handler(ApiError, api_error_handler)
app.include_router(policies_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
