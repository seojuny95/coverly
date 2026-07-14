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
    response = _client().post(
        "/portfolio/analysis", json={"policies": [], "age": 35, "gender": "여성"}
    )

    assert response.status_code == 200
    assert response.json()["status"] == "empty"
    assert response.json()["demographics"] == {
        "age": 35,
        "gender": "여성",
        "source": "user",
        "status": "user_provided",
    }
    assert "counselor" in response.json()


def test_analysis_route_accepts_bounded_personal_context() -> None:
    response = _client().post(
        "/portfolio/analysis",
        json={
            "policies": [],
            "age": 35,
            "gender": "여성",
            "personal_context": [
                {
                    "question": "치료 중 필요한 생활비는 얼마인가요?",
                    "answer": "매달 250만원 정도예요.",
                }
            ],
        },
    )

    assert response.status_code == 200
    assert "personal_context" not in response.json()


def test_analysis_route_verifies_policy_demographics_instead_of_client_source() -> None:
    response = _client().post(
        "/portfolio/analysis",
        json={
            "policies": [
                {
                    "id": "p1",
                    "기본정보": {
                        "보험분류": "질병",
                        "피보험자정보": {
                            "나이": 35,
                            "성별": "여성",
                            "생애단계": "성인",
                        },
                    },
                    "보장목록": [],
                }
            ],
            "demographics": {"age": 70, "gender": "남성", "source": "policy"},
        },
    )

    assert response.status_code == 200
    assert response.json()["demographics"] == {
        "age": 35,
        "gender": "여성",
        "source": "policy",
        "status": "verified_policy",
    }


def test_qa_stream_route_contract() -> None:
    response = _client().post(
        "/qa/stream",
        json={
            "question": "보험 목록 알려줘",
            "policies": [],
            "demographics": {"age": 35, "gender": "여성", "source": "policy"},
            "history": [{"role": "user", "content": "안녕"}],
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert '"type": "meta"' in response.text
    assert '"type": "end"' in response.text
    assert '"status": "no_data"' in response.text


def test_qa_stream_route_validates_blank_question() -> None:
    response = _client().post("/qa/stream", json={"question": "", "policies": []})

    assert response.status_code == 422
