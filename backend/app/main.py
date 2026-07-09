from fastapi import FastAPI

from app.routes.policies import router as policies_router

app = FastAPI(title="Coverly API")
app.include_router(policies_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
