from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.policies import router as policies_router

app = FastAPI(title="Coverly API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(policies_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
