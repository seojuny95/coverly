from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes.analysis import router as analysis_router
from app.routes.qa import router as qa_router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(analysis_router)
    app.include_router(qa_router)
    return TestClient(app)


def test_analysis_route_contract() -> None:
    response = _client().post("/portfolio/analysis", json={"policies": []})

    assert response.status_code == 200
    assert response.json()["status"] == "empty"


def test_qa_route_contract() -> None:
    response = _client().post(
        "/qa",
        json={"question": "보험 목록 알려줘", "policies": []},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "no_data"


def test_qa_route_validates_blank_question() -> None:
    response = _client().post("/qa", json={"question": "", "policies": []})

    assert response.status_code == 422
