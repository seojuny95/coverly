from fastapi import FastAPI

app = FastAPI(title="Coverly API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
