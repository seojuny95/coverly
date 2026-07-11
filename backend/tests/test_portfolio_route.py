from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes.portfolio import router


def test_coverage_summary_route_accepts_parse_result_shape() -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        "/portfolio/summary",
        json={
            "policies": [
                {
                    "id": "p1",
                    "기본정보": {"보험사": "보험사A", "보험분류": "건강보험"},
                    "보장목록": [
                        {
                            "담보명": "암진단비",
                            "가입금액": "1천만원",
                            "보장내용": None,
                            "해설": None,
                        }
                    ],
                    "분석상태": "완료",
                }
            ]
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["totals"][0]["category"] == "암진단비"
    assert body["totals"][0]["totalAmount"] == 10_000_000
    assert body["totals"][0]["coverageCount"] == 1
    assert body["totals"][0]["composition"][0]["policy_id"] == "p1"
