from collections.abc import Mapping
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_PDF_DIR = REPO_ROOT / "sample-insurance-input"
EXPECTED_PATH = SAMPLE_PDF_DIR / "expected-policy-summary.local.json"

REQUIRED_DISPLAY_VALUES = {
    "DB운전자보험증권.pdf": {
        "보험사": "DB손해보험",
        "상품명": "무배당 프로미라이프 참좋은운전자상해보험(TM)2404",
        "증권번호": "POLICY-TEST-MASKED-001",
        "계약자": "테스트고객A",
        "피보험자": "테스트고객A",
        "보험기간.시작일": "2024-07-26",
        "보험기간.종료일": "2044-07-26",
        "만기일": "2044-07-26",
        "보험료.금액": 11670,
        "보험료.납입주기": "월납",
        "납입기간": "20년납",
        "보험분류": "배상·화재·기타",
        # 상해 is evidence-based: the policy's head lists 상해 benefits (후유장해 등).
        "상품태그": ["상해", "운전자"],
    },
    "NH농협보험증권.pdf": {
        "보험사": "NH농협손해보험",
        "상품명": "(무) NH가성비굿플러스어린이보험[1종:해지환급금미지급형]2004",
        "증권번호": "POLICY-TEST-LOCAL-002",
        "계약자": "테스트고객A",
        "피보험자": "테스트고객A",
        "보험기간.시작일": "2020-04-29",
        "보험기간.종료일": "2095-04-29",
        "만기일": "2095-04-29",
        "보험료.금액": 42615,
        "보험료.납입주기": "월납",
        "납입기간": "20년납",
        "보험분류": "상해·질병·실손",
        "상품태그": ["암", "상해", "질병", "어린이"],
    },
    "현대해상자동차보험.pdf": {
        "보험사": "현대해상화재보험",
        "상품명": "Hicar 다이렉트개인용",
        "증권번호": "POLICY-TEST-MASKED-003",
        "계약자": "테스트고객A",
        "피보험자": "테스트고객A",
        "보험기간.시작일": "2026-06-27",
        "보험기간.종료일": "2027-06-27",
        "보험료.금액": 1402890,
        "보험분류": "자동차",
        "상품태그": ["자동차"],
    },
    "흥국보험증권.pdf": {
        "보험사": "흥국화재",
        "상품명": "무배당 흥국화재 맘편한 자녀사랑보험(20.04)_4종(해지환급 미지급형III)",
        "증권번호": "POLICY-TEST-LOCAL-004",
        "계약자": "테스트고객A",
        "피보험자": "테스트고객A",
        "보험기간.시작일": "2020-05-06",
        "보험기간.종료일": "2095-05-06",
        "만기일": "2095-05-06",
        "보험료.금액": 79032,
        "보험료.납입주기": "월납",
        "납입기간": "20년납",
        "보험분류": "상해·질병·실손",
        "상품태그": ["암", "상해", "질병", "어린이"],
    },
}


def flatten_summary(summary: Mapping[str, object], prefix: str = "") -> dict[str, object]:
    flattened: dict[str, object] = {}
    for key, value in summary.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            flattened.update(flatten_summary(value, path))
            continue
        flattened[path] = value

    return flattened
