# backend — 프로젝트 가이드

FastAPI + uv 백엔드. 전체 프로젝트 가이드: [../AGENTS.md](../AGENTS.md).

> `CLAUDE.md`는 이 파일을 가리키는 symlink다.

## 프로젝트 소개

보험 증권 처리, 보장 구조화, 진단, 약관 기반 Q&A를 담당하는 백엔드 앱이다. 엔드포인트는 두 갈래다: 증권 1건을 처리하는 파싱 파이프라인(`POST /policies/parse`)과, 파싱 결과 여러 건을 묶어 다루는 포트폴리오 기능(`POST /portfolio/summary`·`/portfolio/analysis`·`POST /qa`).

## Development Commands

```bash
uv sync
uv run uvicorn app.main:app --reload
uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest
```

## Project Structure

`app/services/`는 도메인이 아니라 **파이프라인 단계 = 파일**로 나눈다. 증권 1건 파싱 계열과 여러 건을 묶는 포트폴리오 계열로 구성된다.

```text
app/
├── main.py                # FastAPI app (4개 라우터 등록)
├── errors.py              # ApiError, request-id 미들웨어
├── routes/
│   ├── policies.py        # POST /policies/parse — 증권 1건 파싱
│   ├── portfolio.py       # POST /portfolio/summary — 보험금 합계
│   ├── analysis.py        # POST /portfolio/analysis — 상담 전 검토
│   └── qa.py              # POST /qa — 근거 기반 Q&A
└── services/
    # 증권 1건 파싱 파이프라인
    ├── types.py           # ParsedDocument, Coverage, PolicySummary 등 도메인 타입
    ├── parsing.py         # pdfplumber 1회 파싱 → ParsedDocument
    ├── classification.py  # 보험종류 분류 (공식 종목 매핑 + LLM fallback)
    ├── summary.py         # 기본정보 (regex 로컬 + LLM 보완)
    ├── grounding.py       # 금액·문구 anti-hallucination (공유)
    ├── coverage.py        # 담보 추출 (표 선택 → LLM 정규화 → grounding)
    ├── explain.py         # 보장내용 없는 담보의 일반 해설
    ├── pipeline.py        # 오케스트레이터: parse → classify+summary → coverage
    ├── coverage_taxonomy.py / coverage_name_matching.py / coverage_name_rules.py
    │                       # 담보명 정규화·대분류·교차 매칭 (합산/중복 판정 근거)
    ├── demographics.py     # 피보험자 나이·성별·생애단계 추출
    # 여러 증권을 묶는 포트폴리오 계열
    ├── portfolio_summary.py       # 보장 합산·실손/중복 구분
    ├── portfolio_analysis.py      # 상담 전 검토 집계 (강점·공백·금액검토)
    ├── portfolio_analysis_generation.py / portfolio_consultation.py
    │                               # 상담사 관점 생성 (LLM + fallback)
    ├── portfolio_demographics.py  # 포트폴리오 단위 인구정보 판정
    ├── portfolio_qa.py / portfolio_qa_generation.py  # Q&A 근거 수집 + 답변 생성
    ├── llm.py             # OpenAI 경계
    └── data/              # insurer_catalog.json, classification_rules.json,
                           # coverage_matching_rules.json
```

전역 원칙(내 편·판매원 아님, grounding)은 [../AGENTS.md](../AGENTS.md)에 있고, 아래는 백엔드에서 그걸 강제하는 규칙이다.

- **특정 보험사·상품 전용 로직 금지.** 코드에 보험사/상품 이름이 등장하면 안 된다. 회사별 차이는 일반 로직(형태 검증, 레이아웃 무관 패턴) + 데이터 파일(`services/data/*.json`)로만 흡수한다. `test_no_insurer_specific_identifiers_in_module`이 이를 강제한다.
- **규칙에 매직넘버 금지.** 분류·판정 규칙은 "용어 존재 여부" 같은 이진 판단만 쓴다. 점수·가중치·임계값이 필요해지는 순간, 그건 규칙이 아니라 LLM fallback으로 보낸다.
- **판매·권유를 생성하지 않는다.** 분석·상담·Q&A 생성(LLM 포함)은 상품 가입 권유나 금액 상향 압박을 출력하지 않는다. 금액 검토는 "적정하다/부족하다"는 단정 대신 "확인해볼 질문"으로 제시한다. (루트 "내 편, 판매원 아님" 원칙의 강제)
- **근거 수준을 응답 구조로 드러낸다.** 확정 판단 대신 확인된 사실 / 일반 가이드 / 확인 불가를 구분한다(예: Q&A 섹션의 `basis`, 금액 검토의 `confidence`). 근거 없이 단정하는 필드를 새로 만들지 않는다. (루트 grounding 원칙의 강제)

## Coding Style & Naming Conventions

- 스타일은 **ruff**에 위임하되, ruff format 통과는 최소선이지 목표가 아니다.
- **가독성 (한눈에 흐름이 잡히게)**: 코드는 훑기만 해도 흐름과 로직이 보여야 한다.
  - 중첩 컴프리헨션·깊은 중첩은 풀어서 루프와 이른 반환(early return)으로 편다.
  - 처리 단계(입력 검증 → 변환 → 출력)마다 빈 줄로 문단을 나눈다.
  - 들여쓰기가 3단을 넘으면 함수를 쪼갠다.
  - 이름은 하는 일을 그대로 드러낸다.
- 타입은 **mypy strict**를 통과해야 한다.
- 라우트는 얇게 유지하고, 외부 I/O와 도메인 로직은 `services/` 아래로 분리한다.
- 마크다운은 한국어, 코드 코멘트·docstring은 영어. 한국어 필드명(담보명 등)은 의도된 데이터 값이다.

## 테스트 정책

- 테스트는 **pytest**, 파일명은 `test_<module>.py`.
- 변경 후 `ruff check`, `ruff format --check`, `mypy`, `pytest`를 모두 통과시킨다.
- **mock 문서는 정확한 추출값을 단언**하고, 실제 샘플(`test_local_*`, gitignored PDF)은 골든 필드 + 불변식(grounding·degrade·응답 shape)을 검증한다.
- **LLM 비용 관리**: 반복(iteration) 중에는 비-LLM 테스트만 돌리고, LLM 의존 테스트(`test_local_*`)는 작업 마무리에 1회만 실행한다.
- **유닛 테스트가 실제 API를 호출하면 안 된다.** LLM 경계는 주입 가능한 completer로 설계하고, 유닛 테스트에서는 stub을 주입한다(예: `test_summary.py`의 autouse fixture). 환경에 `OPENAI_API_KEY`가 있어도 유닛 테스트는 결정적이어야 한다.

## Configuration

- Python 버전은 `.python-version`의 3.12를 따른다.
- 시크릿과 실제 증권 원본은 커밋하지 않는다.

