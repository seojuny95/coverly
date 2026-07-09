# 보장(담보) 내용 추출·표시 — 설계 (Phase 1)

## 목표

보험증권 PDF에서 담보(보장) 목록을 추출해 분석 화면에 표시한다. 각 담보는 담보명·가입금액·보장내용(증권 원문)을 가지며, 증권에 보장내용이 없는 담보는 LLM이 생성한 일반 설명으로 임시로 채운다.

**Phase 2(범위 밖)**: 표준약관 RAG 기반 근거 설명. 이번에 생성하는 일반 설명은 Phase 2에서 표준약관 근거 설명으로 교체한다. 그때까지 생성 설명은 "표준약관 근거"라고 주장하지 않고 일반 설명임을 정직하게 안내한다.

## 배경

- 상위 폴더 `insurance` POC가 같은 샘플 증권 4종으로 담보 추출을 검증했다(pdfplumber 표 추출 → LLM 구조화 → 담보별 설명). POC를 그대로 복사하지 않고 속도·비용을 개선해 이식한다.
- POC의 비용 문제: 업로드 1건당 LLM 호출이 추출 1회 + 담보별 설명 N회. 설명이 매 업로드마다 재생성된다.

## 데이터 구조

`/policies/parse` 응답에 두 필드를 추가한다 (기존 필드 불변):

```json
{
  "status": "accepted",
  "문자수": 12345,
  "기본정보": { ... },
  "보장목록": [
    {
      "담보명": "암진단비",
      "가입금액": "3,000만원",
      "보장내용": "암으로 진단 확정 시 ...",
      "해설": null
    },
    {
      "담보명": "교통사고처리지원금",
      "가입금액": "확인필요",
      "보장내용": null,
      "해설": "교통사고로 형사합의가 필요할 때 ..."
    }
  ],
  "분석상태": "완료"
}
```

- **담보명** (string): 증권 표기 기준. 지급방식·계약형태 부가어("감액없음", "기본계약(...)" 래퍼)는 제거하되, 보장 범위를 가르는 수식어("유사암제외", "80%이상")는 유지.
- **가입금액** (string): 증권 원문 표기. 없거나 근거 불충분이면 `"확인필요"`.
- **보장내용** (string | null): 증권 원문 그대로 (요약 금지). 없으면 null.
- **해설** (string | null): 보장내용이 없는 담보에만 LLM 일반 설명 (1~2문장, 해요체). 생성 실패 시 null.
- **분석상태** (`"완료"` | `"부분"`): 담보 추출·설명 단계가 하나라도 실패하면 `"부분"`. 기본정보 응답은 담보 추출 실패와 무관하게 유지된다.
- `약정구분`(주계약/특약)·`지급유형`은 이번 범위에서 제외 (YAGNI).

## 추출 파이프라인

### 1. 담보표 감지 (pdfplumber, 3단계)

증권은 담보를 괘선 표로 렌더하므로 `pdfplumber.extract_tables()`(기본 lines 전략)로 표를 뜨고, 셀 텍스트의 헤더 키워드로 담보표를 판정한다. 오류 비용이 비대칭이므로(미탐 = 보장목록 통째 손실, 오탐 = 토큰 낭비 소량) 단계적으로 완화한다:

1. **1차 — 이름 AND 금액 헤더**: 이름류(`보장명·담보명·담보종목·보장상세·특약명`)와 금액류(`가입금액·보험가입금액·보장금액·보험금액·한도`)가 모두 있는 표만 선택. 샘플 4종 전부 이 단계에서 잡힘(실측 검증).
2. **2차 — 1차 0건이면 이름 헤더만**: 금액 열 이름이 특이한 증권 커버.
3. **3차 — 그래도 0건이면 레이아웃 텍스트 전체**(`extract_text(layout=True)` + 전체 표 마크다운)를 LLM 입력으로 사용. 최악의 경우가 "표 감지 없는 baseline"과 동일해지는 구조.

선택된 표는 마크다운 표로 직렬화(셀 내 개행은 ` / `)해 이어붙인다. 판정 함수는 순수 함수(`rows -> bool`)로 분리해 pdfplumber 없이 단위 테스트한다.

기존 `pdf_text.py`(pypdf, 기본정보용)는 건드리지 않는다. 라우트가 PDF bytes를 담보 파이프라인에 별도로 전달한다.

### 2. LLM 구조화 (호출 1회)

담보표 마크다운을 structured output(`responses.parse` + pydantic 스키마)으로 `보장목록` 행에 매핑한다. 모델은 `settings.openai_model`(gpt-4.1-mini), temperature 0. 프롬프트 지시:

- 표에 실제로 있는 담보만 전사, 새로 만들지 않는다.
- 보장내용은 원문 그대로(※ 단서 포함), 없으면 null.
- 담보명 부가어 제거 규칙(위 데이터 구조 참조).

### 3. 금액 그라운딩 (환각 방지)

LLM이 반환한 가입금액의 숫자열이 원문 소스의 숫자열에 없으면 `"확인필요"`로 강등한다. 표 헤더가 만원 단위(`(만원)`, `단위: 만원`)를 선언하고 셀이 단위 없는 숫자면 `3,000 → 3,000만원`으로 단위를 명시한다. (POC `amount_grounded`·만원 규칙 이식)

### 4. 임시 설명 생성 (배치 1회 + 캐시)

보장내용이 null인 담보명을 모아 **한 번의 배치 호출**로 설명을 생성한다 (POC의 담보별 N회 호출 대체).

- **캐시**: 일반 설명은 특정 증권에 종속되지 않으므로 담보명 키의 인프로세스 dict 캐시로 재사용한다. 캐시 미스인 이름만 배치 호출에 포함.
- **프롬프트**: 일반적으로 알려진 보장 내용만 1~2문장 해요체로. 금액·면책기간은 단정하지 않고 "보통", "상품마다 다를 수 있어요"로 헤지.
- **best-effort**: 호출 실패 시 해설은 null로 두고 `분석상태 = "부분"`. 업로드는 깨지지 않는다.

### 5. 동시 실행

라우트에서 기존 기본정보 추출(`extract_policy_summary`)과 담보 파이프라인을 `asyncio.gather`(+`asyncio.to_thread`)로 동시에 실행한다. 업로드 지연 = 두 파이프라인의 최대값.

**비용 요약**: 업로드당 LLM 호출 최대 2회(추출 1 + 배치 설명 1), 캐시 웜업 후 사실상 1회. LLM 입력은 담보표 마크다운만(전체 텍스트 대비 ~10배 절약).

## 백엔드 구성

서비스를 도메인 폴더로 나눈다. 폴더 네임스페이스가 생기므로 파일명의 중복 접두사(`policy_`)를 뗀다. `pdf_text.py`(공유 PDF 유틸)와 `llm.py`(공유 completer 헬퍼)는 루트에 둔다.

```text
app/services/
├── pdf_text.py             # (기존) 공유: pypdf 평문 추출
├── llm.py                  # (신규) 공유: structured completer 헬퍼 (주입 가능)
├── policy/                 # (기존 파일 이동)
│   ├── summary.py          # ← policy_summary.py
│   ├── summary_local.py    # ← policy_summary_local.py
│   ├── summary_types.py    # ← policy_summary_types.py
│   ├── llm_extraction.py   # ← policy_llm_extraction.py
│   ├── classification.py   # ← policy_classification.py
│   ├── classification_rules.json
│   └── insurer_catalog.json
└── coverage/               # (신규)
    ├── types.py            # Coverage 스키마 + LLM 추출 스키마
    ├── table.py            # pdfplumber I/O + 순수 판정/직렬화 (3단계 감지)
    ├── amount.py           # 금액 그라운딩 + 만원 단위 규칙 (POC 이식·축소)
    ├── normalize.py        # 담보표 마크다운 -> list[Coverage] (completer 주입)
    ├── explain.py          # 누락 담보 배치 설명 + 담보명 캐시 (completer 주입)
    └── extraction.py       # 오케스트레이터: bytes -> (보장목록, 상태)
app/routes/policies.py      # gather로 기본정보·담보 동시 실행, 응답 확장
```

**기존 파일 이동 (선행 단계, 동작 변경 없음)**: 위 `policy/` 이동에 맞춰 import 경로를 갱신한다.
- 소비처: `routes/policies.py`(`app.services.policy.summary`), 이동 파일 내부 상호 import, 그리고 기존 테스트 7개(`test_policy_*`, `test_local_policy_*`)의 `app.services.policy_*` → `app.services.policy.*`.
- json 로드는 `Path(__file__).with_name(...)` 방식이라 json을 같은 폴더로 옮기면 그대로 동작한다.
- 이 이동만 먼저 커밋해 `pytest`가 통과하는지 확인한 뒤 신규 기능을 얹는다.

- 새 의존성: `pdfplumber` 1개.
- 모든 LLM 경계는 completer 함수 주입으로 분리해 네트워크 없이 테스트한다.
- 실패 격리: 담보 파이프라인의 어떤 예외도 업로드 응답을 깨지 않는다(빈 보장목록 + `"부분"`).

## 프론트엔드 구성

- `upload-policy.ts`: `PolicyCoverage` 타입 + `PolicyUploadResult.보장목록?` 추가.
- `policy-coverage-list.tsx` (신규, `features/policy-analysis/`): 담보 목록 렌더.
  - **담보 1건은 세로 스택**으로, 위에서 아래 순서를 고정한다:
    1. **보장명**(담보명) — 강조(굵게).
    2. **보장설명**(보장내용, 증권 원문) — 있을 때만.
    3. **보장해설**(해설, LLM 생성) — 보장내용이 없을 때만. 즉 2·3은 상호배타이나 렌더 순서상 해설은 설명 자리 아래에 온다.
    4. **보장금액**(가입금액) — 맨 아래.
  - **줄바꿈·가독성**: 보장설명/보장해설은 긴 문장·원문 개행(` / `로 직렬화된 항목 포함)이 뭉치지 않도록 문단으로 렌더한다. `whitespace-pre-line`(원문 개행 보존) + `break-words` + 적절한 `leading`(줄간격)으로 스캔 가능하게. 담보 간에는 구분선/여백으로 카드를 분리한다.
  - 생성 해설(보장해설)에는 안내 라벨: **"일반적인 설명이에요. 정확한 보장 내용은 가입한 상품의 약관에서 확인할 수 있어요."** (UX_COPY 해요체·근거 수준 노출 원칙)
  - `가입금액 === "확인필요"`는 금액 강조 없이 "확인이 필요해요"로 표시.
  - 빈 상태: "이 증권에서 보장 내용을 찾지 못했어요."
- `analysis-page.tsx`: `PolicyDetail`의 기본정보 아래에 `PolicyCoverageList` 렌더. (analysis-page가 이미 크므로 컴포넌트는 별도 파일)

## 테스트 전략 (TDD — 테스트 먼저)

각 단계에서 실패하는 테스트를 먼저 쓰고 구현한다.

**백엔드 (pytest, 네트워크 없음)**

1. `test_coverage_table.py` — 순수 판정: 이름+금액 헤더 표 선택, 오탐 제외(보험료 납입면제·유의사항 표), 2차 완화, 3차 fallback, 마크다운 직렬화.
2. `test_coverage_amount.py` — 그라운딩: 원문에 없는 금액 강등, 만원 단위 명시, 무한/한도 통과.
3. `test_coverage_normalize.py` — fake completer로 행 매핑, 담보명 부가어 제거는 프롬프트 책임이므로 스키마·강등 로직 검증 중심.
4. `test_coverage_explain.py` — 배치 호출에 캐시 미스만 포함, 캐시 적중 시 호출 0회, 실패 시 null.
5. `test_coverage_extraction.py` / `test_policy_upload.py` 확장 — 오케스트레이터 상태 전파, 라우트 응답에 보장목록·분석상태, 담보 실패에도 기본정보 유지.
6. `test_local_coverage_pdfs.py` — 로컬 샘플 4종(gitignore된 실증권)에서 1차 감지 성공 + 보장목록 non-empty (기존 `test_local_*` 패턴, LLM 키 없으면 skip).

**프론트엔드 (Vitest + Testing Library)**

7. `policy-coverage-list.test.tsx` — 담보 행 렌더, 원문/생성 설명 구분(안내 라벨은 생성에만), 확인필요 표기, 빈 상태.

**검증 게이트**: `ruff check` · `ruff format --check` · `mypy`(strict) · `pytest` / `pnpm test` · `lint` · `typecheck` · `format:check` · `build`.

## 결정 기록

- **pdfplumber 채택** (opendataloader-pdf·Docling·pymupdf4llm 비교 결과): 순수 파이썬·MIT·POC 동일 샘플 검증. opendataloader는 JVM 의존, Docling은 torch 모델로 무겁고, pymupdf4llm은 AGPL. 표준약관 RAG(Phase 2)에서 추출기 요구가 커지면 재평가.
- **설명 배치 + 캐시** (POC의 담보별 호출 대체): 호출 수 1+N → ≤2.
- **추출을 LLM 없이 휴리스틱으로 하지 않음**: 병합 제목 행·2행 헤더에서 깨짐. 표만 잘라 보내는 mini 호출이 견고성 대비 저렴.
- **설명을 추출 호출에 인라인하지 않음**: 전사·생성 분리(정확도) + 캐시 가능(비용).
- **`services/policy/`·`services/coverage/` 폴더 분리**: 기존 플랫 `policy_*` 파일을 `policy/`로 이동하고 접두사 제거, 신규 담보 코드는 `coverage/`로. 관리성. 이동은 동작 변경 없는 선행 커밋으로 분리.
- **담보 카드 세로 순서 = 보장명 → 보장설명 → 보장해설 → 보장금액**: 설명을 금액 위에 두어 "무엇을 보장하는지" 먼저 읽히게. 원문 개행 보존으로 가독성 확보.
