import os
from collections.abc import Callable

import pytest

# Unit tests must remain deterministic even when a developer has DATABASE_URL configured.
os.environ["REFERENCE_DATA_DATABASE_ENABLED"] = "false"


_REFERENCE_DATA_ROWS: dict[str, object] = {
    "insurer_catalog": [
        "AXA손해보험",
        "DB손해보험",
        "메리츠화재",
        "KDB생명",
        "한화손해보험",
        "교보생명",
        "삼성화재",
        "흥국생명",
        "흥국화재",
        "현대해상화재보험",
        "KB손해보험",
        "미래에셋생명",
        "더케이손해보험",
        "롯데손해보험",
        "캐롯손해보험",
        "메트라이프생명",
        "하나손해보험",
        "MG손해보험",
        "예별손해보험",
        "NH농협생명",
        "NH농협손해보험",
        "AIA생명",
        "ABL생명",
    ],
    "claim_channels": {
        "보험사": [
            {
                "보험사": "삼성화재",
                "고객센터": "1588-5114",
                "홈페이지": "https://www.samsungfire.com",
                "청구링크": "https://www.samsungfire.com",
                "앱": "삼성화재",
                "비고": "홈페이지 > 보험금청구",
                "source": "https://www.samsungfire.com",
            },
            {
                "보험사": "현대해상",
                "고객센터": "1588-5656",
                "홈페이지": "https://www.hi.co.kr",
                "청구링크": "https://www.hi.co.kr",
                "앱": "현대해상 모바일 앱",
                "source": "https://www.hi.co.kr",
            },
            {
                "보험사": "DB손해보험",
                "고객센터": "1588-0100",
                "홈페이지": "https://www.idbins.com",
                "청구링크": "https://www.idbins.com",
                "앱": "DB손해보험",
                "source": "https://m.directdb.co.kr/comm/spt/serviceGuideView.do",
            },
            {
                "보험사": "메리츠화재",
                "고객센터": "1566-7711",
                "홈페이지": "https://www.meritzfire.com",
                "청구링크": "https://www.meritzfire.com",
                "source": "https://www.meritzfire.com",
            },
            {
                "보험사": "흥국화재",
                "고객센터": "1688-1688",
                "홈페이지": "https://www.heungkukfire.co.kr",
                "청구링크": "https://www.heungkukfire.co.kr/FRW/compensation/carCompInfo.do",
                "source": "https://www.heungkukfire.co.kr",
            },
        ],
        "실손": {
            "이름": "실손24",
            "설명": "실손보험금 청구 공식 서비스",
            "콜센터": "1811-3000",
            "채널": [
                {"이름": "실손24 홈페이지", "링크": "https://www.silson24.or.kr"},
            ],
        },
    },
    "disclosure_links": {
        "association_links": [
            {
                "kind": "life",
                "name": "생명보험협회 공시실",
                "url": "https://www.klia.or.kr/",
                "description": "생명보험 상품공시와 약관 확인 경로",
            },
            {
                "kind": "non_life",
                "name": "손해보험협회 소비자포털 공시정보",
                "url": "https://consumer.knia.or.kr/disclosure.do",
                "description": "손해보험 상품공시와 약관 확인 경로",
            },
            {
                "kind": "integrated",
                "name": "보험다모아",
                "url": "https://e-insmarket.or.kr/",
                "description": "보험상품 비교공시 경로",
            },
        ],
    },
    "essential_coverage_guides": {
        "sources": [
            {
                "id": "kca_funeral_cost_2004",
                "label": "한국소비자원 · 평균 장례비용 조사",
                "url": "https://www.kca.go.kr/home/sub.do?menukey=4002&mode=view&no=1000396173&page=148",
                "published_at": "2004-09-22",
                "reliability": "official",
                "caveat": "장례비용은 시기, 지역, 장례 방식에 따라 달라질 수 있어요.",
            },
            {
                "id": "bizwatch_cancer_diagnosis_2024_07",
                "label": "비즈워치 · 암 진단비 평균 범위",
                "url": "https://news.bizwatch.co.kr/article/finance/2024/07/05/0038",
                "published_at": "2024-07-06",
                "reliability": "private_guidance",
                "caveat": "암 진단비 금액은 소득, 가족 부양, 보험료 부담에 따라 달라질 수 있어요.",
            },
            {
                "id": "banksalad_three_diagnosis_2026",
                "label": "뱅크샐러드 · 3대 진단비 구성 예시",
                "url": "https://www.banksalad.com/articles/%EB%B3%B4%ED%97%98-%EC%A2%85%ED%95%A9%EB%B3%B4%ED%97%98-%EC%A7%88%EB%B3%B4%ED%97%98",
                "published_at": "2026-07-01",
                "reliability": "private_guidance",
                "caveat": "구성 예시는 상품과 개인 상황에 따라 달라질 수 있어요.",
            },
            {
                "id": "silson24_official",
                "label": "실손24 · 서비스 안내",
                "url": "https://www.silson24.or.kr",
                "published_at": "2025-01-01",
                "reliability": "official",
                "caveat": (
                    "실손 청구 가능 범위는 의료기관과 보험회사 시스템에 따라 달라질 수 있어요."
                ),
            },
        ],
        "items": [
            {
                "kind": "death",
                "reference_min_amount": 10_000_000,
                "reference_max_amount": 20_000_000,
                "basis": "장례비와 초기 정리 비용을 먼저 보는 점검용 범위",
                "source_ids": ["kca_funeral_cost_2004"],
            },
            {
                "kind": "cancer",
                "reference_min_amount": 30_000_000,
                "reference_max_amount": 50_000_000,
                "basis": "암 진단비는 치료 중 쉬는 기간의 생활비 성격까지 고려하는 기본 범위",
                "source_ids": [
                    "bizwatch_cancer_diagnosis_2024_07",
                    "banksalad_three_diagnosis_2026",
                ],
            },
            {
                "kind": "cerebrovascular",
                "reference_min_amount": 10_000_000,
                "reference_max_amount": 20_000_000,
                "basis": "뇌혈관질환 진단비는 재활, 간병, 후유장해 가능성을 고려하는 기본 범위",
                "source_ids": ["banksalad_three_diagnosis_2026"],
            },
            {
                "kind": "ischemic_heart",
                "reference_min_amount": 10_000_000,
                "reference_max_amount": 20_000_000,
                "basis": (
                    "심장질환 진단비는 시술, 수술, 입원으로 생길 수 있는 "
                    "소득 공백을 고려하는 기본 범위"
                ),
                "source_ids": ["banksalad_three_diagnosis_2026"],
            },
            {
                "kind": "indemnity",
                "reference_min_amount": None,
                "reference_max_amount": None,
                "basis": "실손은 금액보다 가입 여부, 세대, 자기부담금, 중복 여부를 확인",
                "source_ids": ["silson24_official"],
            },
        ],
    },
}


def _cache_clear(target: Callable[..., object]) -> None:
    cache_clear = getattr(target, "cache_clear", None)
    if callable(cache_clear):
        cache_clear()


@pytest.fixture(autouse=True)
def database_reference_data(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide deterministic Supabase-owned reference rows to unit tests."""

    from app.modules.coverage import disclosure_links
    from app.modules.policy.summary import catalog
    from app.modules.portfolio import essential_guides
    from app.modules.qa import claim_channels
    from app.modules.reference_data import loader as reference_data

    _cache_clear(reference_data._database_reference_data)
    _cache_clear(disclosure_links._directory)
    _cache_clear(claim_channels._directory)
    _cache_clear(catalog.get_insurer_candidates)
    _cache_clear(catalog.get_insurer_aliases)
    _cache_clear(catalog.get_insurer_contact_evidence)
    _cache_clear(essential_guides.essential_coverage_guides)

    monkeypatch.setattr(reference_data, "_database_reference_data", lambda: _REFERENCE_DATA_ROWS)
