import os
from collections.abc import Callable

import pytest

# Unit tests must remain deterministic even when a developer has DATABASE_URL configured.
os.environ["REFERENCE_DATA_DATABASE_ENABLED"] = "false"


_REFERENCE_DATA_ROWS: dict[str, object] = {
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
    from app.modules.qa import claim_channels
    from app.modules.reference_data import loader as reference_data

    _cache_clear(reference_data._database_reference_data)
    _cache_clear(disclosure_links._directory)
    _cache_clear(claim_channels._directory)
    _cache_clear(catalog.get_insurer_contact_evidence)

    monkeypatch.setattr(reference_data, "_database_reference_data", lambda: _REFERENCE_DATA_ROWS)
