from app.services.coverage.normalize import normalize_coverages

SOURCE = (
    "| 보장명 | 보장상세 | 가입금액 |\n"
    "| --- | --- | --- |\n"
    "| 암진단비(감액없음) | 암 진단 확정 시 최초 1회 지급 | 30,000,000원 |\n"
    "| 교통사고처리지원금 |  | 50,000,000원 |"
)


def test_normalize_maps_rows_into_coverages() -> None:
    def fake_complete(system: str, user: str) -> dict[str, object]:
        return {
            "보장목록": [
                {
                    "담보명": "암진단비",
                    "보장내용": "암 진단 확정 시 최초 1회 지급",
                    "가입금액": "30,000,000원",
                },
                {"담보명": "교통사고처리지원금", "보장내용": None, "가입금액": "50,000,000원"},
            ]
        }

    result = normalize_coverages(SOURCE, complete=fake_complete)

    assert result == [
        {
            "담보명": "암진단비",
            "가입금액": "30,000,000원",
            "보장내용": "암 진단 확정 시 최초 1회 지급",
            "해설": None,
        },
        {
            "담보명": "교통사고처리지원금",
            "가입금액": "50,000,000원",
            "보장내용": None,
            "해설": None,
        },
    ]


def test_normalize_demotes_hallucinated_amounts() -> None:
    def fake_complete(system: str, user: str) -> dict[str, object]:
        return {
            "보장목록": [
                {"담보명": "암진단비", "보장내용": None, "가입금액": "77,777,777원"},
            ]
        }

    result = normalize_coverages(SOURCE, complete=fake_complete)

    assert result[0]["가입금액"] == "확인필요"


def test_normalize_skips_invalid_rows() -> None:
    def fake_complete(system: str, user: str) -> dict[str, object]:
        return {
            "보장목록": [
                {"보장내용": "담보명이 없는 행", "가입금액": "1,000원"},
                {"담보명": "정상담보", "보장내용": None, "가입금액": ""},
                "행이 아님",
            ]
        }

    result = normalize_coverages(SOURCE, complete=fake_complete)

    assert [coverage["담보명"] for coverage in result] == ["정상담보"]
    assert result[0]["가입금액"] == "확인필요"  # empty cell -> nothing to show


def test_normalize_returns_no_coverages_for_blank_source() -> None:
    # Even if the model would return rows, a blank source has no coverages to show.
    def fake_complete(system: str, user: str) -> dict[str, object]:
        return {"보장목록": [{"담보명": "지어낸담보", "보장내용": None, "가입금액": "1원"}]}

    assert normalize_coverages("   ", complete=fake_complete) == []
