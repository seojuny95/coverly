# 보장(담보) 내용 추출·표시 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 보험증권 PDF에서 담보(보장) 목록을 추출해 `/policies/parse` 응답에 담고, 분석 화면에 보장명 → 보장설명 → 보장해설 → 보장금액 순서로 표시한다. 증권에 보장내용이 없는 담보는 LLM 일반 설명으로 임시로 채운다.

**Architecture:** pdfplumber로 담보표를 3단계(이름+금액 헤더 → 이름만 → 레이아웃 텍스트)로 감지해 마크다운으로 직렬화하고, LLM structured output 1회로 행을 구조화한 뒤 금액을 원문 그라운딩으로 검증한다. 보장내용 없는 담보명은 배치 1회 + 인프로세스 캐시로 설명을 생성한다. 기존 기본정보 추출과 담보 파이프라인은 `asyncio.gather`로 동시 실행한다.

**Tech Stack:** FastAPI + uv + pdfplumber(신규) + OpenAI Responses API(structured outputs) / Next.js(App Router) + Vitest + Testing Library.

**Spec:** [docs/superpowers/specs/2026-07-10-coverage-extraction-design.md](../specs/2026-07-10-coverage-extraction-design.md)

## Global Constraints

- 마크다운·PR 본문·UI 카피는 한국어, 코드 코멘트·docstring·커밋 메시지는 영어 (CLAUDE.md).
- 백엔드 게이트: `uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest` 전부 통과. mypy는 **strict**.
- 프론트 게이트: `pnpm test && pnpm lint && pnpm typecheck && pnpm format:check && pnpm build` 전부 통과.
- 백엔드 명령은 `cd backend`, 프론트 명령은 `cd frontend`에서 실행한다.
- 새 파이썬 의존성은 `pdfplumber` 1개만. 추가 금지.
- LLM 모델·키는 `app.settings.get_settings()`(`openai_model="gpt-4.1-mini"`)만 사용, temperature 0.
- API 응답의 새 필드: `보장목록`(list), `분석상태`(`"완료"` | `"부분"`). 기존 필드(`status`, `문자수`, `기본정보`)는 불변.
- 담보 파이프라인의 어떤 실패도 업로드 응답을 깨면 안 된다 (빈 보장목록 + `"부분"`으로 강등).
- 생성 해설 안내 문구(정확히 이 문자열): `일반적인 설명이에요. 정확한 보장 내용은 가입한 상품의 약관에서 확인할 수 있어요.`
- 빈 상태 문구: `이 증권에서 보장 내용을 찾지 못했어요.`
- 실증권 샘플(`sample-insurance-input/`)은 gitignore 대상 — 절대 커밋하지 않는다.
- **전체 작업은 1개 PR**: 전용 브랜치 하나에서 작업한다. 커밋은 태스크마다(=작업 단위) 끊는다. 커밋 메시지 끝에 `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- **테스트가 통과하지 않으면 멈추고 사용자에게 묻는다**: 테스트를 작성하고 구현했는데 그 테스트가 통과하지 않으면(추출 품질 미달 포함), 임의로 계속 고치지 말고 멈춰서 어떻게 할지 사용자에게 확인한다.
- **테스트는 기능 기준**: 관찰 가능한 결과(추출된 보장목록·상태·API 응답·렌더 결과)만 단언한다. 내부 헬퍼·사설 캐시·LLM 호출 횟수를 검증하지 않는다. LLM 경계는 불가피한 경우에만 함수 주입(fake)으로 대체하고, fake의 호출 여부가 아니라 반환 결과를 단언한다.

---

### Task 1: `services/policy/` 폴더 이동 (동작 변경 없음)

기존 플랫 `policy_*` 파일을 `app/services/policy/`로 옮기고 접두사를 뗀다. 코드 수정은 import 경로 갱신뿐이다.

**Files:**
- Move: `backend/app/services/policy_summary.py` → `backend/app/services/policy/summary.py`
- Move: `backend/app/services/policy_summary_local.py` → `backend/app/services/policy/summary_local.py`
- Move: `backend/app/services/policy_summary_types.py` → `backend/app/services/policy/summary_types.py`
- Move: `backend/app/services/policy_llm_extraction.py` → `backend/app/services/policy/llm_extraction.py`
- Move: `backend/app/services/policy_classification.py` → `backend/app/services/policy/classification.py`
- Move: `backend/app/services/policy_classification_rules.json` → `backend/app/services/policy/classification_rules.json`
- Move: `backend/app/services/insurer_catalog.json` → `backend/app/services/policy/insurer_catalog.json`
- Create: `backend/app/services/policy/__init__.py` (빈 파일)
- Modify: `backend/app/routes/policies.py` (import 1줄)
- Modify: `backend/tests/` 아래 `app.services.policy_*`를 import하는 테스트 전부

**Interfaces:**
- Produces: `from app.services.policy.summary import extract_policy_summary` — 이후 태스크(라우트)가 이 경로를 사용. 함수 시그니처는 변경 없음.

- [ ] **Step 1: git mv로 파일 이동 + 패키지 init 생성**

```bash
cd backend
mkdir -p app/services/policy
git mv app/services/policy_summary.py app/services/policy/summary.py
git mv app/services/policy_summary_local.py app/services/policy/summary_local.py
git mv app/services/policy_summary_types.py app/services/policy/summary_types.py
git mv app/services/policy_llm_extraction.py app/services/policy/llm_extraction.py
git mv app/services/policy_classification.py app/services/policy/classification.py
git mv app/services/policy_classification_rules.json app/services/policy/classification_rules.json
git mv app/services/insurer_catalog.json app/services/policy/insurer_catalog.json
touch app/services/policy/__init__.py
git add app/services/policy/__init__.py
```

JSON은 `Path(__file__).with_name(...)`으로 로드되므로 같은 폴더로 옮기면 코드 수정이 필요 없다. 단, `classification.py`의 `_RULES_PATH`는 파일명이 `policy_classification_rules.json` → `classification_rules.json`으로 바뀌므로 해당 상수만 수정한다 (Step 2).

- [ ] **Step 2: import 경로 일괄 갱신**

각 파일에서 아래와 같이 바꾼다 (기계적 치환):

| 파일 | 변경 |
|---|---|
| `app/services/policy/summary.py` | `from app.services.policy_classification import` → `from app.services.policy.classification import`, `from app.services.policy_llm_extraction import` → `from app.services.policy.llm_extraction import`, `from app.services.policy_summary_local import` → `from app.services.policy.summary_local import`, `from app.services.policy_summary_types import` → `from app.services.policy.summary_types import` |
| `app/services/policy/summary_local.py` | `from app.services.policy_summary_types import` → `from app.services.policy.summary_types import` |
| `app/services/policy/llm_extraction.py` | `from app.services.policy_summary_types import` → `from app.services.policy.summary_types import` |
| `app/services/policy/classification.py` | `_RULES_PATH = Path(__file__).with_name("policy_classification_rules.json")` → `_RULES_PATH = Path(__file__).with_name("classification_rules.json")` |
| `app/routes/policies.py` | `from app.services.policy_summary import extract_policy_summary` → `from app.services.policy.summary import extract_policy_summary` |
| `tests/test_policy_summary.py`, `tests/test_policy_contract_terms.py` | `from app.services.policy_summary import` → `from app.services.policy.summary import` |
| `tests/test_policy_classification.py` | `from app.services.policy_classification import` → `from app.services.policy.classification import` |
| `tests/test_policy_llm_extraction.py` | `from app.services.policy_llm_extraction import` → `from app.services.policy.llm_extraction import` |
| `tests/test_local_policy_classification_pdfs.py` | `policy_classification`·`policy_summary` import 2건 동일 규칙으로 |
| `tests/test_local_policy_contract_terms_pdfs.py`, `tests/test_local_policy_summary_quality.py` | `from app.services.policy_summary import` → `from app.services.policy.summary import` |

- [ ] **Step 3: 잔여 참조 없음 확인**

```bash
cd backend && grep -rn "services.policy_" app tests
```

Expected: 출력 없음 (exit 1). 위 표에 없는 파일이 걸리면(예: `tests/test_local_sample_pdfs.py`) 같은 규칙(`app.services.policy_X` → `app.services.policy.X`)으로 갱신한다.

- [ ] **Step 4: 전체 게이트 실행**

```bash
cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest
```

Expected: 전부 통과 (로컬 샘플 테스트 포함 — 샘플 폴더가 있으면 실행됨).

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "refactor: move policy services into services/policy package

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: `coverage/table.py` — 담보표 감지·직렬화 (pdfplumber 도입)

**Files:**
- Modify: `backend/pyproject.toml` (pdfplumber 의존성)
- Create: `backend/app/services/coverage/__init__.py` (빈 파일)
- Create: `backend/app/services/coverage/table.py`
- Test: `backend/tests/test_coverage_table.py`

**Interfaces:**
- Produces:
  - `extract_coverage_source(pdf_bytes: bytes) -> str` — 담보표 감지·직렬화의 유일한 공개 함수. 담보표 마크다운, 없으면 전체 표 마크다운 + 레이아웃 텍스트. 감지 헬퍼는 모듈 내부(언더스코어)라 계약이 아니다.

**테스트 원칙:** 표 감지는 손으로 만든 행 리스트(내 키워드 목록을 미러링)가 아니라 **실제 샘플 증권**으로 검증한다 — 관찰 가능한 기능("이 증권에서 담보표 소스를 뽑아낸다")을 테스트한다. 샘플이 없으면 skip(기존 `test_local_*` 패턴). 실행 시 `sample-insurance-input/`가 로컬에 있어야 red→green을 관찰할 수 있다.

- [ ] **Step 1: pdfplumber 의존성 추가**

```bash
cd backend && uv add "pdfplumber>=0.11"
```

- [ ] **Step 2: 실패하는 테스트 작성**

`backend/tests/test_coverage_table.py`:

```python
"""Coverage-table extraction against the real (gitignored) sample policies.

Detection is validated on real documents, not synthetic row lists — a
hand-crafted table that contains the exact header keywords would just mirror the
implementation. The behavior under test is: given a real policy PDF, produce a
markdown coverage-table source the LLM can map.
"""

import pytest

from app.services.coverage.table import extract_coverage_source
from tests.summary_helpers import SAMPLE_PDF_DIR

pytestmark = pytest.mark.skipif(
    not SAMPLE_PDF_DIR.exists(), reason="local sample PDFs are not available"
)

SAMPLE_FILENAMES = [
    "DB운전자보험증권.pdf",
    "NH농협보험증권.pdf",
    "현대해상자동차보험.pdf",
    "흥국보험증권.pdf",
]

_AMOUNT_HEADERS = ("가입금액", "보험가입금액", "보장금액", "보험금액", "한도")


@pytest.mark.parametrize("filename", SAMPLE_FILENAMES)
def test_extracts_markdown_coverage_source_from_real_policy(filename: str) -> None:
    source = extract_coverage_source((SAMPLE_PDF_DIR / filename).read_bytes())

    # A coverage table was detected and serialized as markdown (starts with a row),
    # and it carries an amount column — i.e. it is the coverage table, not prose.
    assert source.startswith("| "), f"{filename}: no markdown coverage table detected"
    assert any(header in source for header in _AMOUNT_HEADERS), (
        f"{filename}: detected table has no amount column"
    )
```

- [ ] **Step 3: 실패 확인**

```bash
cd backend && uv run pytest tests/test_coverage_table.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.coverage'` (샘플이 로컬에 있으면 4건 수집 후 실패; 없으면 skip)

- [ ] **Step 4: 구현**

`backend/app/services/coverage/__init__.py`: 빈 파일.

`backend/app/services/coverage/table.py`:

```python
"""Coverage (담보) table detection and serialization.

Real policies render the coverage list as ruled tables, so pdfplumber's default
lines strategy recovers them. Detection is tiered because the failure costs are
asymmetric — a missed table loses the whole coverage list, while a spurious one
only adds a few prompt tokens the LLM is told to ignore:

1. strict: a table whose cells contain both a name header and an amount header
2. relaxed: name header only (unusual amount column labels)
3. fallback: no match at all -> every table as markdown + layout text, so the
   worst case equals the no-detection baseline

Only extract_coverage_source is public; the tiering/serialization helpers are
internal (their behavior is covered end-to-end via extract_coverage_source on
real sample policies).
"""

import io

import pdfplumber

_TableRows = list[list[str | None]]

# Header vocabulary observed across sample policies, kept intentionally wider
# than the samples so unseen insurers still match tier 1.
_NAME_HEADERS = ("보장명", "담보명", "담보종목", "보장상세", "특약명")
_AMOUNT_HEADERS = ("가입금액", "보험가입금액", "보장금액", "보험금액", "한도")


def _flatten(rows: _TableRows) -> str:
    return " ".join(cell or "" for row in rows for cell in row)


def _is_coverage_table(rows: _TableRows, *, require_amount: bool = True) -> bool:
    """True when the table's cells carry coverage headers (merged title rows OK)."""
    flat = _flatten(rows)
    if not any(header in flat for header in _NAME_HEADERS):
        return False
    return not require_amount or any(header in flat for header in _AMOUNT_HEADERS)


def _select_coverage_tables(tables: list[_TableRows]) -> list[_TableRows]:
    """Coverage tables by tiered matching: strict (name+amount) first, then name-only."""
    strict = [table for table in tables if _is_coverage_table(table)]
    if strict:
        return strict
    return [table for table in tables if _is_coverage_table(table, require_amount=False)]


def _serialize_table(rows: _TableRows) -> str:
    """Render a pdfplumber table as markdown so column-row associations survive.

    Cell-internal newlines become ' / ' (cells often pack several line items).
    Returns '' for non-tables (<2 rows or <2 columns).
    """
    clean = [[(cell or "").replace("\n", " / ").strip() for cell in row] for row in rows]
    clean = [row for row in clean if any(row)]
    if len(clean) < 2 or len(clean[0]) < 2:
        return ""
    width = len(clean[0])
    lines = [
        "| " + " | ".join(clean[0]) + " |",
        "| " + " | ".join(["---"] * width) + " |",
    ]
    for row in clean[1:]:
        cells = (row + [""] * width)[:width]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def extract_coverage_source(pdf_bytes: bytes) -> str:
    """LLM input for coverage extraction, via the tiered detection above."""
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        tables = [table for page in pdf.pages for table in page.extract_tables()]
        selected = _select_coverage_tables(tables)
        if selected:
            parts = [md for table in selected if (md := _serialize_table(table))]
            return "\n\n".join(parts)
        # Tier 3: no coverage table detected — hand the LLM everything we have.
        parts = [md for table in tables if (md := _serialize_table(table))]
        parts.extend(page.extract_text(layout=True) or "" for page in pdf.pages)
        return "\n".join(parts).strip()
```

- [ ] **Step 5: 테스트·타입 통과 확인**

```bash
cd backend && uv run pytest tests/test_coverage_table.py -v && uv run mypy .
```

Expected: 테스트 전부 PASS. mypy가 `pdfplumber` 스텁 누락(`import-untyped`)을 보고하면 `backend/pyproject.toml`의 `[tool.mypy]` 아래에 추가:

```toml
[[tool.mypy.overrides]]
module = ["pdfplumber", "pdfplumber.*"]
ignore_missing_imports = true
```

그 후 `uv run mypy .` 재실행 → 통과.

- [ ] **Step 6: Commit**

```bash
cd backend && git add -A && git commit -m "feat: add tiered coverage table detection with pdfplumber

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: `coverage/amount.py` — 금액 그라운딩·만원 단위

**Files:**
- Create: `backend/app/services/coverage/amount.py`
- Test: `backend/tests/test_coverage_amount.py`

**Interfaces:**
- Produces:
  - `AMOUNT_UNVERIFIED = "확인필요"` (모듈 상수)
  - `normalize_amount(value: str, source: str) -> str` — 그라운딩 실패·빈 값이면 `"확인필요"`, 만원 단위 표는 `3,000` → `3,000만원`, 그 외 원문 유지

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/test_coverage_amount.py`:

```python
from app.services.coverage.amount import AMOUNT_UNVERIFIED, normalize_amount

MAN_UNIT_SOURCE = "| 보장명 | 가입금액 (만원) |\n| --- | --- |\n| 암진단비 | 3,000 |"
WON_SOURCE = "| 보장명 | 가입금액 |\n| --- | --- |\n| 상해사망 | 10,000,000원 |"


def test_amount_kept_when_grounded_in_source() -> None:
    assert normalize_amount("10,000,000원", WON_SOURCE) == "10,000,000원"


def test_amount_demoted_when_not_in_source() -> None:
    # 99,999,999 appears nowhere in the source digits -> likely hallucinated.
    assert normalize_amount("99,999,999원", WON_SOURCE) == AMOUNT_UNVERIFIED


def test_empty_amount_demoted() -> None:
    assert normalize_amount("", WON_SOURCE) == AMOUNT_UNVERIFIED
    assert normalize_amount("   ", WON_SOURCE) == AMOUNT_UNVERIFIED


def test_non_numeric_amount_passes_grounding() -> None:
    # 무한/한도-style values carry no digits to verify; keep them verbatim.
    assert normalize_amount("무한", WON_SOURCE) == "무한"


def test_bare_amount_under_man_unit_header_gets_explicit_unit() -> None:
    assert normalize_amount("3,000", MAN_UNIT_SOURCE) == "3,000만원"


def test_amount_with_unit_is_not_reformatted() -> None:
    source = MAN_UNIT_SOURCE + "\n| 상해사망 | 1억원 |"
    assert normalize_amount("1억원", source) == "1억원"


def test_grounding_ignores_commas_and_whitespace() -> None:
    source = "| 보장명 | 가입금액 |\n| --- | --- |\n| 상해사망 | 10000000원 |"
    assert normalize_amount("10,000,000원", source) == "10,000,000원"
```

- [ ] **Step 2: 실패 확인**

```bash
cd backend && uv run pytest tests/test_coverage_amount.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.coverage.amount'`

- [ ] **Step 3: 구현**

`backend/app/services/coverage/amount.py`:

```python
"""Amount grounding for extracted coverages (anti-hallucination).

A digital policy has an exact text layer, so any amount we surface must appear
in the extraction source verbatim (digit-sequence match, tolerant of commas and
unit reformatting). An amount that does not is likely an LLM hallucination from
layout confusion — demote it to 확인필요 instead of asserting it.

Some tables declare the unit once in the header ("가입금액 (만원)") and print
bare numbers in cells; make the unit explicit so the display is unambiguous.
"""

import re

AMOUNT_UNVERIFIED = "확인필요"

_MAN_UNIT_HEADER = re.compile(r"\(\s*(?:단위\s*[:：]?\s*)?만원\s*\)|단위\s*[:：]\s*만원")
_BARE_AMOUNT = re.compile(r"^\d[\d,]*$")


def _digits(text: str) -> str:
    return re.sub(r"\D", "", text)


def normalize_amount(value: str, source: str) -> str:
    """Grounded display amount: verbatim value, 만원-unit made explicit, or 확인필요."""
    cleaned = value.strip()
    if not cleaned:
        return AMOUNT_UNVERIFIED
    digits = _digits(cleaned)
    if digits and digits not in _digits(source):
        return AMOUNT_UNVERIFIED
    if _MAN_UNIT_HEADER.search(source) and _BARE_AMOUNT.match(cleaned):
        return f"{int(cleaned.replace(',', '')):,}만원"
    return cleaned
```

- [ ] **Step 4: 통과 확인**

```bash
cd backend && uv run pytest tests/test_coverage_amount.py -v && uv run mypy .
```

Expected: 전부 PASS.

- [ ] **Step 5: Commit**

```bash
cd backend && git add -A && git commit -m "feat: ground coverage amounts against extraction source

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: `llm.py` + `coverage/types.py` + `coverage/normalize.py` — LLM 구조화

**Files:**
- Create: `backend/app/services/llm.py`
- Create: `backend/app/services/coverage/types.py`
- Create: `backend/app/services/coverage/normalize.py`
- Test: `backend/tests/test_coverage_normalize.py`

**Interfaces:**
- Consumes: `normalize_amount(value, source)` (Task 3)
- Produces:
  - `JsonCompleter = Callable[[str, str], dict[str, object]]` (`app.services.llm`)
  - `structured_completer(schema: type[BaseModel]) -> JsonCompleter` — 키 없거나 API 실패 시 **raise** (호출자가 격리)
  - `Coverage` TypedDict (`app.services.coverage.types`): `담보명: str`, `가입금액: str`, `보장내용: str | None`, `해설: str | None` — 모든 키 항상 존재
  - `normalize_coverages(source: str, complete: JsonCompleter | None = None) -> list[Coverage]`

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/test_coverage_normalize.py`:

```python
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
```

- [ ] **Step 2: 실패 확인**

```bash
cd backend && uv run pytest tests/test_coverage_normalize.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 구현 (파일 3개)**

`backend/app/services/llm.py`:

```python
"""Thin OpenAI boundary shared by coverage services.

Isolates the network call behind the JsonCompleter type so services stay
testable — tests inject a plain function instead of hitting the API. Raises on
a missing key or API failure; callers isolate failures (the coverage pipeline
degrades to 확인필요/부분 instead of breaking the upload).
"""

from collections.abc import Callable
from functools import lru_cache
from typing import Any, cast

from openai import OpenAI
from pydantic import BaseModel

from app.settings import get_settings

JsonCompleter = Callable[[str, str], dict[str, object]]

_TIMEOUT_S = 30.0
_MAX_RETRIES = 2


@lru_cache
def _get_client(api_key: str) -> OpenAI:
    return OpenAI(api_key=api_key, timeout=_TIMEOUT_S, max_retries=_MAX_RETRIES)


def structured_completer(schema: type[BaseModel]) -> JsonCompleter:
    """Build a completer that constrains the model's output to `schema`."""

    def complete(system: str, user: str) -> dict[str, object]:
        settings = get_settings()
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        response = _get_client(settings.openai_api_key).responses.parse(
            model=settings.openai_model,
            input=cast(
                Any,
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            ),
            text_format=schema,
            temperature=0,
        )
        parsed = response.output_parsed
        return parsed.model_dump(mode="json") if parsed else {}

    return complete
```

`backend/app/services/coverage/types.py`:

```python
from typing import TypedDict


class Coverage(TypedDict):
    """One coverage (담보) row for the /policies/parse response.

    보장내용 is the policy's own wording (authoritative); 해설 is an LLM-generated
    general explanation, filled only when 보장내용 is absent.
    """

    담보명: str
    가입금액: str
    보장내용: str | None
    해설: str | None
```

`backend/app/services/coverage/normalize.py`:

```python
"""Normalize a coverage-table source into the unified Coverage shape.

Insurers print the coverage table with different columns; one structured-output
LLM call maps any layout into the same fields. The LLM only transcribes rows
that exist in the source — amounts it returns are then grounded against the
source and demoted to 확인필요 when unverifiable (see amount.normalize_amount).
"""

from functools import lru_cache

from pydantic import BaseModel, ValidationError

from app.services.coverage.amount import normalize_amount
from app.services.coverage.types import Coverage
from app.services.llm import JsonCompleter, structured_completer

_SYSTEM = (
    "너는 보험 증권의 담보(보장) 표를 통일된 형식으로 정리하는 도우미다. "
    "입력은 증권에서 추출한 담보표 마크다운(또는 레이아웃 텍스트)이다. "
    "열 제목(보장명·담보명·담보종목·보장상세·보장내용·가입금액 등)을 보고 각 값을 정확히 매핑하라. "
    "표에 실제로 있는 담보만 옮기고 새로 지어내지 마라. "
    "담보명은 증권 표기를 살리되, 보장 대상·사고를 바꾸지 않는 순수 부가어는 괄호 안이라도 제거한다 "
    "— '감액없음'·'감액'·'기본계약'·'주계약'·'선택'·'무배당' 같은 지급방식·계약형태 표시. "
    "예: '암진단비(유사암제외)(감액없음)'→'암진단비(유사암제외)'. "
    "'기본계약(일반상해후유장해(80%이상))'처럼 담보명을 감싸는 접두 래퍼는 바깥 래퍼만 벗긴다. "
    "반대로 '유사암제외'·'80%이상'·'1~5종'처럼 보장 범위·지급조건을 가르는 수식어는 반드시 남긴다. "
    "보장내용은 증권 원문 그대로 옮긴다(요약·축약 금지, '※'로 시작하는 단서 포함). 없으면 null. "
    "가입금액이 없으면 빈 문자열로 둔다."
)


class _CoverageRow(BaseModel):
    담보명: str
    보장내용: str | None
    가입금액: str


class _CoverageList(BaseModel):
    보장목록: list[_CoverageRow]


@lru_cache
def _default_completer() -> JsonCompleter:
    return structured_completer(_CoverageList)


def normalize_coverages(source: str, complete: JsonCompleter | None = None) -> list[Coverage]:
    """Map a coverage-table source into Coverages (one structured LLM call)."""
    if not source.strip():
        return []
    completer = complete or _default_completer()
    rows = completer(_SYSTEM, source).get("보장목록", [])
    if not isinstance(rows, list):
        return []

    coverages: list[Coverage] = []
    for row in rows:
        try:
            parsed = _CoverageRow.model_validate(row)
        except ValidationError:
            continue
        detail = parsed.보장내용.strip() if parsed.보장내용 else None
        coverages.append(
            Coverage(
                담보명=parsed.담보명.strip(),
                가입금액=normalize_amount(parsed.가입금액, source),
                보장내용=detail or None,
                해설=None,
            )
        )
    return coverages
```

- [ ] **Step 4: 통과 확인**

```bash
cd backend && uv run pytest tests/test_coverage_normalize.py -v && uv run mypy .
```

Expected: 전부 PASS.

- [ ] **Step 5: Commit**

```bash
cd backend && git add -A && git commit -m "feat: normalize coverage tables via structured LLM extraction

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: `coverage/explain.py` — 배치 설명 + 담보명 캐시

**Files:**
- Create: `backend/app/services/coverage/explain.py`
- Test: `backend/tests/test_coverage_explain.py`

**Interfaces:**
- Consumes: `JsonCompleter`, `structured_completer` (Task 4)
- Produces: `explain_coverages(names: list[str], complete: JsonCompleter | None = None) -> tuple[dict[str, str], bool]` — `(담보명 → 해설, ok)`. LLM 실패 시 그때까지 모은 설명 + `ok=False`. 절대 raise하지 않음. (배치 1회 호출 + 담보명 인프로세스 캐시는 내부 비용 최적화 — 계약 아님, 테스트 대상 아님.)

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/test_coverage_explain.py`:

These tests assert only the observable result — the `(담보명 → 해설, ok)` returned to the caller. They never inspect the cache or count LLM calls (batching/caching are cost optimizations verified by review, not behavior). Each test uses **unique 담보명** so the in-process cache can't couple tests to each other.

```python
from app.services.coverage.explain import explain_coverages


def test_generates_an_explanation_for_a_coverage_name() -> None:
    def fake_complete(system: str, user: str) -> dict[str, object]:
        return {"설명목록": [{"담보명": "가입설명담보", "해설": "이런 상황에 보험금을 드려요."}]}

    explanations, ok = explain_coverages(["가입설명담보"], complete=fake_complete)

    assert ok is True
    assert explanations == {"가입설명담보": "이런 상황에 보험금을 드려요."}


def test_explains_every_requested_name() -> None:
    def fake_complete(system: str, user: str) -> dict[str, object]:
        return {
            "설명목록": [
                {"담보명": "다중설명담보A", "해설": "A 설명이에요."},
                {"담보명": "다중설명담보B", "해설": "B 설명이에요."},
            ]
        }

    explanations, ok = explain_coverages(
        ["다중설명담보A", "다중설명담보B"], complete=fake_complete
    )

    assert ok is True
    assert explanations == {"다중설명담보A": "A 설명이에요.", "다중설명담보B": "B 설명이에요."}


def test_reports_not_ok_when_the_llm_fails() -> None:
    def failing_complete(system: str, user: str) -> dict[str, object]:
        raise RuntimeError("API down")

    explanations, ok = explain_coverages(["실패담보"], complete=failing_complete)

    assert ok is False  # lets the caller degrade to 분석상태=부분
    assert "실패담보" not in explanations


def test_omits_names_the_llm_cannot_explain() -> None:
    def fake_complete(system: str, user: str) -> dict[str, object]:
        return {"설명목록": []}

    explanations, ok = explain_coverages(["설명불가능담보"], complete=fake_complete)

    assert ok is True
    assert explanations == {}


def test_no_names_yields_no_explanations() -> None:
    def fake_complete(system: str, user: str) -> dict[str, object]:
        return {"설명목록": [{"담보명": "지어낸담보", "해설": "호출되면 안 돼요."}]}

    assert explain_coverages([], complete=fake_complete) == ({}, True)
```

- [ ] **Step 2: 실패 확인**

```bash
cd backend && uv run pytest tests/test_coverage_explain.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 구현**

`backend/app/services/coverage/explain.py`:

```python
"""General explanations for coverages whose 보장내용 is absent (Phase 1, interim).

One batched structured-output call explains every cache-missed name; results
are cached in-process by 담보명 because a general explanation is independent of
any particular policy. Phase 2 replaces these with 표준약관-grounded
explanations — until then the frontend labels them honestly as general.

Never raises: on LLM failure the caller gets cache hits plus ok=False so the
upload degrades to 분석상태=부분 instead of breaking.
"""

from functools import lru_cache

from pydantic import BaseModel, ValidationError

from app.services.llm import JsonCompleter, structured_completer

_SYSTEM = (
    "너는 표준적인 보험 담보를 일반적으로 설명하는 도우미다. "
    "목록의 각 담보가 일반적으로 무엇을 보장하는지 전문용어 없이 쉬운 말과 "
    "친근한 존댓말(~해요체)로 1~2문장씩 설명하라. "
    "금액·정확한 면책기간·감액률은 단정하지 말고 '보통', '상품마다 다를 수 있어요'처럼 표현하라. "
    "지어내지 말고 일반적으로 알려진 내용만 써라. "
    "일반적으로 알려진 내용이 없는 담보는 결과에서 제외하라."
)


class _Explanation(BaseModel):
    담보명: str
    해설: str


class _ExplanationBatch(BaseModel):
    설명목록: list[_Explanation]


_CACHE: dict[str, str] = {}


@lru_cache
def _default_completer() -> JsonCompleter:
    return structured_completer(_ExplanationBatch)


def explain_coverages(
    names: list[str], complete: JsonCompleter | None = None
) -> tuple[dict[str, str], bool]:
    """(담보명 -> 해설, ok): cache-first, one batch LLM call for the misses."""
    unique = list(dict.fromkeys(name.strip() for name in names if name.strip()))
    explanations = {name: _CACHE[name] for name in unique if name in _CACHE}
    missing = [name for name in unique if name not in _CACHE]
    if not missing:
        return explanations, True

    completer = complete or _default_completer()
    try:
        payload = completer(_SYSTEM, "\n".join(f"- {name}" for name in missing))
    except Exception:
        return explanations, False

    rows = payload.get("설명목록", [])
    if not isinstance(rows, list):
        return explanations, True
    for row in rows:
        try:
            parsed = _Explanation.model_validate(row)
        except ValidationError:
            continue
        name, text = parsed.담보명.strip(), parsed.해설.strip()
        if name in missing and text:
            _CACHE[name] = text
            explanations[name] = text
    return explanations, True
```

- [ ] **Step 4: 통과 확인**

```bash
cd backend && uv run pytest tests/test_coverage_explain.py -v && uv run mypy .
```

Expected: 전부 PASS.

- [ ] **Step 5: Commit**

```bash
cd backend && git add -A && git commit -m "feat: add batched cached coverage explanations

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: `coverage/extraction.py` — 오케스트레이터

**Files:**
- Create: `backend/app/services/coverage/extraction.py`
- Test: `backend/tests/test_coverage_extraction.py`

**Interfaces:**
- Consumes: `extract_coverage_source` (Task 2), `normalize_coverages` (Task 4), `explain_coverages` (Task 5)
- Produces:
  - `STATUS_OK = "완료"`, `STATUS_PARTIAL = "부분"` (모듈 상수)
  - `extract_coverages(pdf_bytes: bytes, *, normalize=..., explain=...) -> tuple[list[Coverage], str]` — **절대 raise하지 않음**. 라우트(Task 7)가 이 시그니처를 사용.

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/test_coverage_extraction.py`:

```python
import pytest

from app.services.coverage import extraction as extraction_module
from app.services.coverage.extraction import STATUS_OK, STATUS_PARTIAL, extract_coverages
from app.services.coverage.types import Coverage


def _coverage(name: str, detail: str | None) -> Coverage:
    return {"담보명": name, "가입금액": "1,000원", "보장내용": detail, "해설": None}


def test_generates_explanation_for_coverage_missing_policy_wording(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(extraction_module, "extract_coverage_source", lambda _b: "| 담보표 |")

    def fake_explain(names: list[str]) -> tuple[dict[str, str], bool]:
        return {name: f"{name} 설명이에요." for name in names}, True

    coverages, status = extract_coverages(
        b"%PDF-",
        normalize=lambda _s: [_coverage("교통사고처리지원금", None)],
        explain=fake_explain,
    )

    assert status == STATUS_OK
    assert coverages[0]["해설"] == "교통사고처리지원금 설명이에요."


def test_policy_wording_is_not_overwritten_by_generated_explanation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(extraction_module, "extract_coverage_source", lambda _b: "| 담보표 |")

    # An explanation is offered for every name, but a coverage that already has
    # policy wording must keep it — 해설 stays None (증권 원문 우선).
    def fake_explain(names: list[str]) -> tuple[dict[str, str], bool]:
        return {name: "지어낸 설명" for name in names}, True

    coverages, status = extract_coverages(
        b"%PDF-",
        normalize=lambda _s: [
            _coverage("암진단비", "암 진단 시 지급"),
            _coverage("교통사고처리지원금", None),
        ],
        explain=fake_explain,
    )

    assert status == STATUS_OK
    assert coverages[0]["보장내용"] == "암 진단 시 지급"
    assert coverages[0]["해설"] is None
    assert coverages[1]["해설"] == "지어낸 설명"


def test_partial_when_explanations_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(extraction_module, "extract_coverage_source", lambda _b: "| 담보표 |")

    coverages, status = extract_coverages(
        b"%PDF-",
        normalize=lambda _s: [_coverage("암진단비", None)],
        explain=lambda _names: ({}, False),
    )

    assert status == STATUS_PARTIAL
    assert coverages[0]["담보명"] == "암진단비"  # coverages are still returned
    assert coverages[0]["해설"] is None


def test_degrades_to_empty_partial_when_normalization_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(extraction_module, "extract_coverage_source", lambda _b: "| 담보표 |")

    def failing_normalize(_source: str) -> list[Coverage]:
        raise RuntimeError("LLM down")

    coverages, status = extract_coverages(b"%PDF-", normalize=failing_normalize)

    assert coverages == []
    assert status == STATUS_PARTIAL


def test_degrades_to_empty_partial_on_unreadable_pdf() -> None:
    # Real pdfplumber path: garbage bytes must never raise out of the pipeline.
    coverages, status = extract_coverages(b"%PDF-broken not a real pdf")

    assert coverages == []
    assert status == STATUS_PARTIAL
```

- [ ] **Step 2: 실패 확인**

```bash
cd backend && uv run pytest tests/test_coverage_extraction.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 구현**

`backend/app/services/coverage/extraction.py`:

```python
"""Coverage pipeline orchestrator: PDF bytes -> (보장목록, 분석상태).

Failure isolation lives here so the upload route stays thin: any error in
table detection or LLM normalization degrades to an empty list + 부분, and an
explanation failure keeps the extracted coverages (해설 stays None). This
function never raises.
"""

from collections.abc import Callable

from app.services.coverage.explain import explain_coverages
from app.services.coverage.normalize import normalize_coverages
from app.services.coverage.table import extract_coverage_source
from app.services.coverage.types import Coverage

STATUS_OK = "완료"
STATUS_PARTIAL = "부분"

Normalizer = Callable[[str], list[Coverage]]
Explainer = Callable[[list[str]], tuple[dict[str, str], bool]]


def extract_coverages(
    pdf_bytes: bytes,
    *,
    normalize: Normalizer = normalize_coverages,
    explain: Explainer = explain_coverages,
) -> tuple[list[Coverage], str]:
    """Extract the coverage list from a policy PDF, best-effort."""
    try:
        coverages = normalize(extract_coverage_source(pdf_bytes))
    except Exception:
        return [], STATUS_PARTIAL

    missing = [c["담보명"] for c in coverages if not c["보장내용"]]
    if not missing:
        return coverages, STATUS_OK

    explanations, ok = explain(missing)
    for coverage in coverages:
        if coverage["보장내용"] is None:
            coverage["해설"] = explanations.get(coverage["담보명"])
    return coverages, STATUS_OK if ok else STATUS_PARTIAL
```

- [ ] **Step 4: 통과 확인**

```bash
cd backend && uv run pytest tests/test_coverage_extraction.py -v && uv run mypy .
```

Expected: 전부 PASS.

- [ ] **Step 5: Commit**

```bash
cd backend && git add -A && git commit -m "feat: orchestrate coverage extraction with failure isolation

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: 라우트 확장 — `보장목록`·`분석상태` + 동시 실행

**Files:**
- Modify: `backend/app/routes/policies.py`
- Test: `backend/tests/test_policy_upload.py` (기존 파일 확장)

**Interfaces:**
- Consumes: `extract_coverages(pdf_bytes) -> tuple[list[Coverage], str]` (Task 6), `extract_policy_summary(text)` (Task 1 경로)
- Produces: `/policies/parse` 응답 = `{status, 문자수, 기본정보, 보장목록, 분석상태}` — 프론트(Task 9)가 이 계약을 사용.

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/test_policy_upload.py`의 기존 `test_parse_accepts_pdf_and_returns_extracted_summary`에 monkeypatch·단언 추가, 그리고 새 테스트 2개 추가:

기존 테스트 수정 — `monkeypatch.setattr(policies, "extract_pdf_text", ...)` 바로 아래에 추가:

```python
    monkeypatch.setattr(policies, "extract_coverages", lambda _data: ([], "완료"))
```

그리고 마지막 단언 뒤에 추가:

```python
    assert payload["보장목록"] == []
    assert payload["분석상태"] == "완료"
```

새 테스트 (파일 끝에 추가):

```python
def test_parse_returns_coverages_with_analysis_status(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.routes import policies

    client = TestClient(app)
    monkeypatch.setattr(policies, "extract_pdf_text", lambda _data: "보험증권 계약자: 가나")
    monkeypatch.setattr(
        policies,
        "extract_coverages",
        lambda _data: (
            [
                {
                    "담보명": "암진단비",
                    "가입금액": "3,000만원",
                    "보장내용": None,
                    "해설": "암으로 진단받으면 약속된 금액을 드려요.",
                }
            ],
            "완료",
        ),
    )

    response = client.post(
        "/policies/parse",
        files={"file": ("policy.pdf", b"%PDF-1.7\n%%EOF", "application/pdf")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["보장목록"] == [
        {
            "담보명": "암진단비",
            "가입금액": "3,000만원",
            "보장내용": None,
            "해설": "암으로 진단받으면 약속된 금액을 드려요.",
        }
    ]
    assert payload["분석상태"] == "완료"


def test_parse_keeps_summary_when_coverage_extraction_is_partial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.routes import policies

    client = TestClient(app)
    monkeypatch.setattr(policies, "extract_pdf_text", lambda _data: "보험사: 삼성화재")
    monkeypatch.setattr(policies, "extract_coverages", lambda _data: ([], "부분"))

    response = client.post(
        "/policies/parse",
        files={"file": ("policy.pdf", b"%PDF-1.7\n%%EOF", "application/pdf")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["기본정보"]["보험사"] == "삼성화재"
    assert payload["보장목록"] == []
    assert payload["분석상태"] == "부분"
```

- [ ] **Step 2: 실패 확인**

```bash
cd backend && uv run pytest tests/test_policy_upload.py -v
```

Expected: 새/수정 테스트 FAIL — `AttributeError: ... has no attribute 'extract_coverages'` 또는 `KeyError: '보장목록'`

- [ ] **Step 3: 라우트 구현**

`backend/app/routes/policies.py` — import에 `import asyncio`와 `from app.services.coverage.extraction import extract_coverages` 추가, `parse_policy`를 다음으로 교체:

```python
@router.post("/parse")
async def parse_policy(file: UploadFile) -> dict[str, object]:
    data = await _read_pdf(file)
    text = extract_pdf_text(data)
    if not text:
        raise ApiError(
            status_code=422,
            code="PDF_TEXT_EXTRACTION_FAILED",
            message="PDF에서 텍스트를 추출할 수 없습니다.",
        )

    # Both pipelines are sync/blocking; run them concurrently off the event loop.
    summary, (coverages, analysis_status) = await asyncio.gather(
        asyncio.to_thread(extract_policy_summary, text),
        asyncio.to_thread(extract_coverages, data),
    )

    return {
        "status": "accepted",
        "문자수": len(text),
        "기본정보": summary,
        "보장목록": coverages,
        "분석상태": analysis_status,
    }
```

- [ ] **Step 4: 통과 확인 + 전체 게이트**

```bash
cd backend && uv run pytest tests/test_policy_upload.py -v
cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest
```

Expected: 전부 PASS.

- [ ] **Step 5: Commit**

```bash
cd backend && git add -A && git commit -m "feat: return coverage list from policy parse endpoint

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: 로컬 샘플 PDF 테스트 (실증권 회귀 방지)

**Files:**
- Test: `backend/tests/test_local_coverage_pdfs.py`

**Interfaces:**
- Consumes: `extract_coverages`, `STATUS_OK` (Task 6), `tests.summary_helpers.SAMPLE_PDF_DIR`

이 태스크는 **기능 전체(PDF → 보장목록)를 실증권으로 검증**하는 회귀 게이트다. Task 2가 담보표 감지(마크다운 소스)를 이미 실샘플로 덮으므로, 여기서는 LLM까지 포함한 끝단 결과만 본다. LLM 비용이 있어 키가 있을 때만 실행(기존 `test_local_*` 정책과 동일).

- [ ] **Step 1: 테스트 작성**

`backend/tests/test_local_coverage_pdfs.py`:

```python
"""End-to-end coverage extraction against the real (gitignored) sample policies.

Costs LLM calls, so it runs only when an OpenAI key is configured (same policy
as the other test_local_ files). This is the quality gate: every sample policy
must yield a non-empty coverage list where each coverage has a name, an amount,
and either policy wording or a generated explanation.
"""

import pytest

from app.services.coverage.extraction import STATUS_OK, extract_coverages
from app.settings import get_settings
from tests.summary_helpers import SAMPLE_PDF_DIR

pytestmark = [
    pytest.mark.skipif(not SAMPLE_PDF_DIR.exists(), reason="local sample PDFs are not available"),
    pytest.mark.skipif(
        not get_settings().openai_api_key, reason="OPENAI_API_KEY is not configured"
    ),
]

SAMPLE_FILENAMES = [
    "DB운전자보험증권.pdf",
    "NH농협보험증권.pdf",
    "현대해상자동차보험.pdf",
    "흥국보험증권.pdf",
]


@pytest.mark.parametrize("filename", SAMPLE_FILENAMES)
def test_local_samples_extract_nonempty_coverages(filename: str) -> None:
    coverages, status = extract_coverages((SAMPLE_PDF_DIR / filename).read_bytes())

    assert status == STATUS_OK
    assert coverages, f"no coverages extracted from {filename}"
    for coverage in coverages:
        assert coverage["담보명"]
        assert coverage["가입금액"]
        assert coverage["보장내용"] or coverage["해설"], (
            f"{filename}::{coverage['담보명']} has neither policy wording nor explanation"
        )
```

- [ ] **Step 2: 실행 (키 설정된 로컬에서)**

```bash
cd backend && uv run pytest tests/test_local_coverage_pdfs.py -v
```

Expected: 실증권 4종의 보장목록이 비어있지 않고, 모든 담보가 보장내용 또는 해설을 가진다. 키가 없으면 skip. 실패하면 (Global Constraints에 따라) **멈추고 사용자에게 보고** — 헤더 어휘·프롬프트 조정은 사용자 확인 후.

- [ ] **Step 3: Commit**

```bash
cd backend && git add tests/test_local_coverage_pdfs.py && git commit -m "test: add local sample coverage extraction regression tests

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 9: 프론트 — 타입 + `PolicyCoverageList` 컴포넌트

**Files:**
- Modify: `frontend/src/features/policy-upload/upload-policy.ts`
- Create: `frontend/src/features/policy-analysis/policy-coverage-list.tsx`
- Test: `frontend/src/features/policy-analysis/policy-coverage-list.test.tsx`

**Interfaces:**
- Consumes: 백엔드 응답 계약 (Task 7)
- Produces:
  - `PolicyCoverage` 타입: `{ 담보명: string; 가입금액: string; 보장내용: string | null; 해설: string | null }`
  - `PolicyUploadResult`에 `보장목록?: PolicyCoverage[]`, `분석상태?: "완료" | "부분"` 추가
  - `PolicyCoverageList({ coverages }: { coverages?: PolicyCoverage[] })` — Task 10이 사용

- [ ] **Step 1: 실패하는 테스트 작성**

`frontend/src/features/policy-analysis/policy-coverage-list.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import { PolicyCoverageList } from "./policy-coverage-list";
import type { PolicyCoverage } from "../policy-upload/upload-policy";

const GENERATED_NOTICE =
  "일반적인 설명이에요. 정확한 보장 내용은 가입한 상품의 약관에서 확인할 수 있어요.";

const withDetail: PolicyCoverage = {
  담보명: "암진단비",
  가입금액: "3,000만원",
  보장내용: "암 진단 확정 시 최초 1회 지급",
  해설: null,
};

const withExplanation: PolicyCoverage = {
  담보명: "교통사고처리지원금",
  가입금액: "5,000만원",
  보장내용: null,
  해설: "교통사고 형사합의금을 지원해요.",
};

const unverifiedAmount: PolicyCoverage = {
  담보명: "긴급출동서비스",
  가입금액: "확인필요",
  보장내용: null,
  해설: null,
};

describe("PolicyCoverageList", () => {
  test("renders name, policy wording, then amount in order", () => {
    render(<PolicyCoverageList coverages={[withDetail]} />);

    const item = screen.getByRole("listitem");
    const text = item.textContent ?? "";
    expect(text.indexOf("암진단비")).toBeGreaterThanOrEqual(0);
    expect(text.indexOf("암진단비")).toBeLessThan(
      text.indexOf("암 진단 확정 시 최초 1회 지급"),
    );
    expect(text.indexOf("암 진단 확정 시 최초 1회 지급")).toBeLessThan(
      text.indexOf("3,000만원"),
    );
  });

  test("keeps policy wording readable with preserved line breaks", () => {
    render(
      <PolicyCoverageList
        coverages={[{ ...withDetail, 보장내용: "지급 사유\n※ 유사암 제외" }]}
      />,
    );

    expect(screen.getByText(/지급 사유/)).toHaveClass("whitespace-pre-line");
  });

  test("does not show the generated notice for policy wording", () => {
    render(<PolicyCoverageList coverages={[withDetail]} />);

    expect(screen.queryByText(GENERATED_NOTICE)).not.toBeInTheDocument();
  });

  test("shows generated explanation with the honest notice", () => {
    render(<PolicyCoverageList coverages={[withExplanation]} />);

    expect(
      screen.getByText("교통사고 형사합의금을 지원해요."),
    ).toBeInTheDocument();
    expect(screen.getByText(GENERATED_NOTICE)).toBeInTheDocument();
  });

  test("renders unverified amounts as a soft ask instead of 확인필요", () => {
    render(<PolicyCoverageList coverages={[unverifiedAmount]} />);

    expect(screen.getByText("가입금액은 확인이 필요해요")).toBeInTheDocument();
    expect(screen.queryByText("확인필요")).not.toBeInTheDocument();
  });

  test("shows the empty state when there are no coverages", () => {
    render(<PolicyCoverageList coverages={[]} />);

    expect(
      screen.getByText("이 증권에서 보장 내용을 찾지 못했어요."),
    ).toBeInTheDocument();
  });

  test("shows the empty state when coverages are missing entirely", () => {
    render(<PolicyCoverageList />);

    expect(
      screen.getByText("이 증권에서 보장 내용을 찾지 못했어요."),
    ).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: 실패 확인**

```bash
cd frontend && pnpm vitest run src/features/policy-analysis/policy-coverage-list.test.tsx
```

Expected: FAIL — `Cannot find module './policy-coverage-list'`

- [ ] **Step 3: 타입 추가 + 컴포넌트 구현**

`frontend/src/features/policy-upload/upload-policy.ts` — `PolicyBasicInfo` 아래에 추가하고 `PolicyUploadResult`를 확장:

```ts
export type PolicyCoverage = {
  담보명: string;
  가입금액: string;
  보장내용: string | null;
  해설: string | null;
};

export type PolicyUploadResult = {
  status: "accepted";
  문자수: number;
  기본정보?: PolicyBasicInfo;
  보장목록?: PolicyCoverage[];
  분석상태?: "완료" | "부분";
};
```

`frontend/src/features/policy-analysis/policy-coverage-list.tsx`:

```tsx
import type { PolicyCoverage } from "../policy-upload/upload-policy";

const GENERATED_NOTICE =
  "일반적인 설명이에요. 정확한 보장 내용은 가입한 상품의 약관에서 확인할 수 있어요.";

type PolicyCoverageListProps = {
  coverages?: PolicyCoverage[];
};

export function PolicyCoverageList({ coverages }: PolicyCoverageListProps) {
  if (!coverages || coverages.length === 0) {
    return (
      <p className="text-sm leading-6 text-[#111827]/60">
        이 증권에서 보장 내용을 찾지 못했어요.
      </p>
    );
  }

  return (
    <ul className="divide-y divide-[#111827]/10">
      {coverages.map((coverage, index) => (
        <li key={`${coverage.담보명}-${index}`} className="py-4 first:pt-0 last:pb-0">
          <p className="text-sm font-semibold break-words text-[#111827]">
            {coverage.담보명}
          </p>
          {coverage.보장내용 ? (
            <p className="mt-1.5 text-sm leading-6 break-words whitespace-pre-line text-[#111827]/75">
              {coverage.보장내용}
            </p>
          ) : coverage.해설 ? (
            <>
              <p className="mt-1.5 text-sm leading-6 break-words whitespace-pre-line text-[#111827]/75">
                {coverage.해설}
              </p>
              <p className="mt-1 text-xs leading-5 text-[#111827]/50">
                {GENERATED_NOTICE}
              </p>
            </>
          ) : null}
          <p className="mt-2 text-sm">
            {coverage.가입금액 === "확인필요" ? (
              <span className="text-[#111827]/60">가입금액은 확인이 필요해요</span>
            ) : (
              <span className="font-medium text-[#111827]">{coverage.가입금액}</span>
            )}
          </p>
        </li>
      ))}
    </ul>
  );
}
```

- [ ] **Step 4: 통과 확인**

```bash
cd frontend && pnpm format && pnpm vitest run src/features/policy-analysis/policy-coverage-list.test.tsx && pnpm typecheck
```

Expected: 전부 PASS (`pnpm format`이 새 파일을 Prettier 규칙으로 정리).

- [ ] **Step 5: Commit**

```bash
cd frontend && git add -A && git commit -m "feat: add policy coverage list component and types

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 10: 분석 화면 통합 + 전체 게이트

**Files:**
- Modify: `frontend/src/features/policy-analysis/analysis-page.tsx` (`PolicyDetail` 함수)

**Interfaces:**
- Consumes: `PolicyCoverageList` (Task 9), `policy.result.보장목록`

- [ ] **Step 1: `PolicyDetail`에 보장 내용 섹션 추가**

`analysis-page.tsx` import에 추가:

```tsx
import { PolicyCoverageList } from "./policy-coverage-list";
```

`PolicyDetail` 컴포넌트의 `</dl>` 닫는 태그 바로 뒤(같은 래퍼 div 안)에 추가:

```tsx
      <div className="mt-6">
        <h3 className="text-xs font-medium text-[#111827]/70">보장 내용</h3>
        <div className="mt-2 rounded-[8px] border border-[#111827]/10 bg-white px-5 py-4">
          <PolicyCoverageList coverages={policy.result.보장목록} />
        </div>
      </div>
```

- [ ] **Step 2: 프론트 전체 게이트**

```bash
cd frontend && pnpm format && pnpm test && pnpm lint && pnpm typecheck && pnpm format:check && pnpm build
```

Expected: 전부 통과.

- [ ] **Step 3: 백엔드 전체 게이트 최종 확인**

```bash
cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest
```

Expected: 전부 통과.

- [ ] **Step 4: 수동 스모크 (선택, 로컬 키 필요)**

```bash
# terminal 1
cd backend && uv run uvicorn app.main:app --reload
# terminal 2
cd frontend && pnpm dev
```

`/upload`에서 샘플 증권 업로드 → 분석 화면에서 담보 카드가 보장명 → 보장설명/보장해설 → 보장금액 순으로 표시되는지, 생성 해설에 안내 문구가 붙는지 확인.

- [ ] **Step 5: Commit**

```bash
cd frontend && git add -A && git commit -m "feat: show coverage list in policy analysis detail

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
