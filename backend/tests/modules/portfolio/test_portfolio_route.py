from fastapi import FastAPI
from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from app.core.errors import ApiError, api_error_handler
from app.modules.portfolio import router as portfolio
from app.modules.portfolio import summary as portfolio_summary
from app.modules.portfolio.overview import SummaryOverviewUnavailableError
from app.modules.portfolio.schemas import PolicyInput, PortfolioCoverageSummary, PortfolioOverview
from app.modules.portfolio.session.dependencies import get_portfolio_session_service
from app.modules.portfolio.session.models import (
    CachedPortfolioAnalysis,
    PortfolioSessionSnapshot,
)
from app.modules.portfolio.session.service import PortfolioSessionUnavailable
from app.modules.reference_data.loader import ReferenceDataUnavailableError

DOCUMENT_1 = "00000000-0000-0000-0000-000000000001"
DOCUMENT_2 = "00000000-0000-0000-0000-000000000002"


def _attach_test_overview(summary: PortfolioCoverageSummary) -> PortfolioCoverageSummary:
    return summary.model_copy(
        update={
            "overview": PortfolioOverview(
                generation="llm",
                title="테스트 총평",
                paragraphs=["확인된 보장 정보를 정리했어요."],
            )
        }
    )


def _client(
    monkeypatch: MonkeyPatch,
    policies: list[dict[str, object] | PolicyInput],
    *,
    stub_overview: bool = True,
) -> TestClient:
    parsed_policies = tuple(
        policy if isinstance(policy, PolicyInput) else PolicyInput.model_validate(policy)
        for policy in policies
    )

    class _Sessions:
        def snapshot(
            self,
            token: str,
            *,
            policy_ids: list[str] | None = None,
        ) -> PortfolioSessionSnapshot:
            assert token == "portfolio-token"
            return PortfolioSessionSnapshot(
                session_id="portfolio-1",
                version=1,
                policies=parsed_policies,
                rag_session_ids=(),
            )

        def load_cached_analysis(
            self,
            snapshot: PortfolioSessionSnapshot,
            *,
            context_hash: str,
        ) -> None:
            return None

        def save_cached_analysis(
            self,
            snapshot: PortfolioSessionSnapshot,
            analysis: CachedPortfolioAnalysis,
        ) -> None:
            return None

    if stub_overview:
        monkeypatch.setattr(portfolio, "attach_summary_overview", _attach_test_overview)
    app = FastAPI()
    app.add_exception_handler(ApiError, api_error_handler)
    app.include_router(portfolio.router)
    app.dependency_overrides[get_portfolio_session_service] = lambda: _Sessions()
    return TestClient(app)


def _request(*policy_ids: str) -> dict[str, object]:
    return {
        "portfolioSessionToken": "portfolio-token",
        "policyIds": list(policy_ids or (DOCUMENT_1,)),
    }


def test_coverage_summary_route_accepts_parse_result_shape(
    monkeypatch: MonkeyPatch,
) -> None:
    policies: list[dict[str, object] | PolicyInput] = [
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
    response = _client(monkeypatch, policies).post(
        "/portfolio/summary",
        json=_request(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["totals"][0]["category"] == "암진단비"
    assert body["totals"][0]["totalAmount"] == 10_000_000
    assert body["totals"][0]["coverageCount"] == 1
    assert body["totals"][0]["composition"][0]["policy_id"] == "p1"
    assert body["premium"]["monthly_total"] == 0
    assert body["overview"] is None


def test_coverage_summary_loads_structured_policies_from_session(
    monkeypatch: MonkeyPatch,
) -> None:
    policy = PolicyInput.model_validate(
        {
            "id": DOCUMENT_1,
            "기본정보": {"보험사": "보험사A", "보험분류": "건강보험"},
            "보장목록": [
                {
                    "담보명": "암진단비",
                    "가입금액": "1천만원",
                    "보장내용": None,
                    "해설": None,
                }
            ],
        }
    )
    saved: list[CachedPortfolioAnalysis] = []

    class _Sessions:
        def snapshot(
            self,
            token: str,
            *,
            policy_ids: list[str] | None = None,
        ) -> PortfolioSessionSnapshot:
            assert token == "portfolio-token"
            assert policy_ids == [DOCUMENT_1.replace("-", "")]
            return PortfolioSessionSnapshot(
                session_id="portfolio-1",
                version=1,
                policies=(policy,),
                rag_session_ids=(),
            )

        def load_cached_analysis(
            self,
            snapshot: PortfolioSessionSnapshot,
            *,
            context_hash: str,
        ) -> None:
            return None

        def save_cached_analysis(
            self,
            snapshot: PortfolioSessionSnapshot,
            analysis: CachedPortfolioAnalysis,
        ) -> None:
            saved.append(analysis)

    monkeypatch.setattr(portfolio, "attach_summary_overview", _attach_test_overview)
    app = FastAPI()
    app.add_exception_handler(ApiError, api_error_handler)
    app.include_router(portfolio.router)
    app.dependency_overrides[get_portfolio_session_service] = lambda: _Sessions()

    response = TestClient(app).post(
        "/portfolio/summary",
        json={
            "portfolioSessionToken": "portfolio-token",
            "policyIds": [DOCUMENT_1],
        },
    )

    assert response.status_code == 200
    assert response.json()["totals"][0]["totalAmount"] == 10_000_000
    assert saved[0].version == 1
    assert saved[0].result["overview"] is None


def test_coverage_summary_maps_cache_store_outage_to_api_error(
    monkeypatch: MonkeyPatch,
) -> None:
    policy = PolicyInput.model_validate(
        {
            "id": DOCUMENT_1,
            "기본정보": {"보험사": "보험사A", "보험분류": "건강보험"},
            "보장목록": [],
        }
    )

    class _Sessions:
        def snapshot(
            self,
            token: str,
            *,
            policy_ids: list[str] | None = None,
        ) -> PortfolioSessionSnapshot:
            return PortfolioSessionSnapshot(
                session_id="portfolio-1",
                version=1,
                policies=(policy,),
                rag_session_ids=(),
            )

        def load_cached_analysis(
            self,
            snapshot: PortfolioSessionSnapshot,
            *,
            context_hash: str,
        ) -> None:
            raise PortfolioSessionUnavailable

    monkeypatch.setattr(portfolio, "attach_summary_overview", _attach_test_overview)
    app = FastAPI()
    app.add_exception_handler(ApiError, api_error_handler)
    app.include_router(portfolio.router)
    app.dependency_overrides[get_portfolio_session_service] = lambda: _Sessions()

    response = TestClient(app).post("/portfolio/summary", json=_request())

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "portfolio_session_unavailable"


def test_coverage_summary_rejects_non_uuid_policy_ids(
    monkeypatch: MonkeyPatch,
) -> None:
    response = _client(monkeypatch, []).post(
        "/portfolio/summary",
        json={
            "portfolioSessionToken": "portfolio-token",
            "policyIds": ["not-a-document-id"],
        },
    )

    assert response.status_code == 422


def test_coverage_summary_route_serializes_curated_alias_group(
    monkeypatch: MonkeyPatch,
) -> None:
    policies: list[dict[str, object] | PolicyInput] = [
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

    response = _client(monkeypatch, policies).post(
        "/portfolio/summary",
        json=_request(DOCUMENT_1, DOCUMENT_2),
    )

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
    policies: list[dict[str, object] | PolicyInput] = [
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
    response = _client(monkeypatch, policies).post(
        "/portfolio/summary",
        json=_request(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["premium"]["monthly_total"] == 90_000
    assert body["premium"]["monthly_policy_count"] == 1
    assert body["premium_benchmark"] is None


def test_summary_route_does_not_generate_llm_overview(
    monkeypatch: MonkeyPatch,
) -> None:
    def fail(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("summary route must not generate overview")

    monkeypatch.setattr(portfolio, "attach_summary_overview", fail)
    policies: list[dict[str, object] | PolicyInput] = [
        {
            "id": DOCUMENT_1,
            "기본정보": {"보험사": "테스트보험사", "보험분류": "건강보험"},
            "보장목록": [{"담보명": "암진단비", "가입금액": "3천만원", "지급유형": "정액"}],
        }
    ]
    response = _client(monkeypatch, policies, stub_overview=False).post(
        "/portfolio/summary",
        json=_request(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["overview"] is None
    assert body["totals"]


def test_summary_overview_route_returns_only_generated_overview(
    monkeypatch: MonkeyPatch,
) -> None:
    policies: list[dict[str, object] | PolicyInput] = [
        {
            "id": DOCUMENT_1,
            "기본정보": {"보험사": "테스트보험사", "보험분류": "건강보험"},
            "보장목록": [{"담보명": "암진단비", "가입금액": "3천만원", "지급유형": "정액"}],
        }
    ]
    response = _client(monkeypatch, policies).post(
        "/portfolio/overview",
        json=_request(),
    )

    assert response.status_code == 200
    assert response.json() == {
        "generation": "llm",
        "title": "테스트 총평",
        "paragraphs": ["확인된 보장 정보를 정리했어요."],
    }


def test_summary_overview_route_returns_retryable_error_when_generation_fails(
    monkeypatch: MonkeyPatch,
) -> None:
    def fail(*_args: object, **_kwargs: object) -> object:
        raise SummaryOverviewUnavailableError("offline")

    monkeypatch.setattr(portfolio, "attach_summary_overview", fail)
    policies: list[dict[str, object] | PolicyInput] = [
        {
            "id": DOCUMENT_1,
            "기본정보": {"보험사": "테스트보험사", "보험분류": "건강보험"},
            "보장목록": [{"담보명": "암진단비", "가입금액": "3천만원", "지급유형": "정액"}],
        }
    ]
    response = _client(monkeypatch, policies, stub_overview=False).post(
        "/portfolio/overview",
        json=_request(),
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "portfolio_overview_unavailable"
    assert response.json()["error"]["message"].startswith("총평을 생성하지 못했어요.")


def test_summary_route_returns_retryable_error_when_reference_data_fails(
    monkeypatch: MonkeyPatch,
) -> None:
    def fail(*_args: object, **_kwargs: object) -> object:
        raise ReferenceDataUnavailableError("offline")

    monkeypatch.setattr(portfolio, "summarize_portfolio_coverages", fail)
    response = _client(monkeypatch, []).post("/portfolio/summary", json=_request())

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "reference_data_unavailable"
