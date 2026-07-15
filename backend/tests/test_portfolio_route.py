from fastapi import FastAPI
from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from app.errors import ApiError, api_error_handler
from app.routes import portfolio
from app.schemas.portfolio import PortfolioCoverageSummary, PortfolioOverview
from app.services.analysis.summary_overview import SummaryOverviewUnavailableError
from app.services.portfolio import summary as portfolio_summary
from app.services.reference_data import ReferenceDataUnavailableError


def _attach_test_overview(summary: PortfolioCoverageSummary) -> PortfolioCoverageSummary:
    return summary.model_copy(
        update={
            "overview": PortfolioOverview(
                generation="llm",
                title="테스트 총평",
                paragraphs=["확인된 보장 정보를 정리했어요."],
                takeaways=[],
            )
        }
    )


def _client(monkeypatch: MonkeyPatch) -> TestClient:
    monkeypatch.setattr(portfolio, "attach_summary_overview", _attach_test_overview)
    app = FastAPI()
    app.add_exception_handler(ApiError, api_error_handler)
    app.include_router(portfolio.router)
    return TestClient(app)


def test_coverage_summary_route_accepts_parse_result_shape(
    monkeypatch: MonkeyPatch,
) -> None:
    response = _client(monkeypatch).post(
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
    assert body["overview"]["generation"] == "llm"


def test_coverage_summary_route_serializes_curated_alias_group(
    monkeypatch: MonkeyPatch,
) -> None:
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

    response = _client(monkeypatch).post("/portfolio/summary", json={"policies": policies})

    assert response.status_code == 200
    total = response.json()["totals"][0]
    assert total["category"] == "허혈성심질환진단비"
    assert total["totalAmount"] == 30_000_000
    assert total["coverageCount"] == 2
    assert {source["coverage_name"] for source in total["composition"]} == {
        "허혈성심장질환진단비",
        "허혈성심질환진단비(감액없음)",
    }


def test_coverage_summary_route_includes_monthly_premium_without_inventing_benchmark(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(portfolio_summary, "premium_benchmark_for_age", lambda _age: None)
    response = _client(monkeypatch).post(
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
    assert body["premium_benchmark"] is None


def test_summary_route_returns_retryable_error_when_llm_overview_fails(
    monkeypatch: MonkeyPatch,
) -> None:
    def fail(*_args: object, **_kwargs: object) -> object:
        raise SummaryOverviewUnavailableError("offline")

    monkeypatch.setattr(portfolio, "attach_summary_overview", fail)
    app = FastAPI()
    app.add_exception_handler(ApiError, api_error_handler)
    app.include_router(portfolio.router)

    response = TestClient(app).post("/portfolio/summary", json={"policies": []})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "portfolio_overview_unavailable"


def test_summary_route_returns_retryable_error_when_reference_data_fails(
    monkeypatch: MonkeyPatch,
) -> None:
    def fail(*_args: object, **_kwargs: object) -> object:
        raise ReferenceDataUnavailableError("offline")

    monkeypatch.setattr(portfolio, "summarize_portfolio_coverages", fail)
    app = FastAPI()
    app.add_exception_handler(ApiError, api_error_handler)
    app.include_router(portfolio.router)

    response = TestClient(app).post("/portfolio/summary", json={"policies": []})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "reference_data_unavailable"
