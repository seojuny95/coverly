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
    assert body["premium"]["monthly_total"] == 0


def test_coverage_summary_route_serializes_curated_alias_group() -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    policies = [
        {
            "id": "p1",
            "기본정보": {"보험사": "보험사A", "보험분류": "건강보험"},
            "보장목록": [
                {
                    "담보명": "허혈성심장질환진단비",
                    "가입금액숫자": 10_000_000,
                    "지급유형": "정액",
                }
            ],
        },
        {
            "id": "p2",
            "기본정보": {"보험사": "보험사B", "보험분류": "건강보험"},
            "보장목록": [
                {
                    "담보명": "허혈성심질환진단비(감액없음)",
                    "가입금액숫자": 20_000_000,
                    "지급유형": "정액",
                }
            ],
        },
    ]

    response = client.post("/portfolio/summary", json={"policies": policies})

    assert response.status_code == 200
    total = response.json()["totals"][0]
    assert total["category"] == "허혈성심질환진단비"
    assert total["totalAmount"] == 30_000_000
    assert total["coverageCount"] == 2
    assert {source["coverage_name"] for source in total["composition"]} == {
        "허혈성심장질환진단비",
        "허혈성심질환진단비(감액없음)",
    }


def test_coverage_summary_route_includes_monthly_premium_benchmark_when_age_is_unique() -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        "/portfolio/summary",
        json={
            "policies": [
                {
                    "id": "p1",
                    "기본정보": {
                        "보험사": "보험사A",
                        "보험분류": "건강보험",
                        "피보험자정보": {
                            "나이": 32,
                            "성별": "남성",
                            "생애단계": "성인",
                        },
                        "보험료": {"금액": 90000, "납입주기": "월납"},
                    },
                    "보장목록": [],
                }
            ]
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["premium"]["monthly_total"] == 90_000
    assert body["premium"]["monthly_policy_count"] == 1
    assert body["premium_benchmark"] is not None
    assert body["premium_benchmark"]["suggested_min_premium"] > 0
