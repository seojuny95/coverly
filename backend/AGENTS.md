# backend — 프로젝트 가이드

FastAPI + uv 백엔드. 전체 프로젝트 가이드: [../AGENTS.md](../AGENTS.md).

> `CLAUDE.md`는 이 파일을 가리키는 symlink다.

## 프로젝트 소개

Coverly AI의 보험 증권 처리, 보장 구조화, 진단, 약관 기반 Q&A를 담당하는 백엔드 앱이다. 분류·상담·Q&A 생성은 결정적 규칙과 LLM(AI)을 함께 써서 근거 기반으로 답한다. 현재 핵심 흐름은 증권 파싱(`POST /policies/parse`), 포트폴리오 보장금 요약(`POST /portfolio/summary`), 근거 기반 Q&A(`POST /qa/stream`)다. 상담용 총평은 서버가 생성하며 프론트엔드는 synthetic fallback을 만들지 않는다. 참조 데이터의 소유권과 운영 경계는 [REFERENCE_DATA.md](REFERENCE_DATA.md)에 정의한다.

## Development Commands

```bash
uv sync
uv run uvicorn app.main:app --reload
uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest
```

## Project Structure

`app/services/`는 런타임 파이프라인과 의존 방향이 드러나도록 나눈다. 핵심 라우트(`parse`, `summary`, `qa`)는 하위 사실 계층(`policy`, `portfolio`, `evidence`, `coverage_knowledge`, `rag`)을 사용하지만, 하위 계층은 라우트나 상위 use case를 import하지 않는다. 새 코드는 아래 패키지 경로를 직접 import한다.

```text
app/
├── main.py                # FastAPI app (핵심 3개 흐름과 보조 라우터 등록)
├── errors.py              # ApiError, request-id 미들웨어
├── routes/
│   ├── policies.py        # POST /policies/parse — 증권 1건 파싱
│   ├── portfolio.py       # POST /portfolio/summary — 보장금 합계
│   └── qa.py              # POST /qa/stream — 근거 기반 Q&A 스트리밍
└── services/
    ├── llm.py             # OpenAI 경계: structured/text/stream completion
    ├── grounding.py       # 금액·문구 anti-hallucination (공유)
    ├── paths.py           # services/data 공통 경로
    ├── data/              # insurer_catalog.json, classification_rules.json 등
    ├── policy/            # 증권 1건 처리
    │   ├── models.py      # ParsedDocument, Coverage, PolicySummary 등 타입
    │   ├── parsing.py     # pdfplumber 1회 파싱 → ParsedDocument
    │   ├── classification.py  # 보험종류 분류 (규칙 + LLM fallback)
    │   ├── demographics.py    # 피보험자 나이·성별·생애단계 추출
    │   ├── pipeline.py        # parse → summary/classification → coverage
    │   ├── summary/service.py # 기본정보 (regex 로컬 + LLM 보완)
    │   └── coverage/
    │       ├── service.py     # 담보 추출 (표 선택 → LLM 정규화 → grounding)
    │       └── explanation.py # 보장내용 없는 담보의 약관/RAG 기반 해설
    ├── coverage_knowledge/
    │   ├── taxonomy.py        # 담보 대분류·생애단계 체크
    │   ├── matching.py        # 담보명 정규화·교차 매칭
    │   ├── rules.py           # coverage_matching_rules.json 로딩/검증
    │   ├── purpose.py         # 담보 목적 설명
    │   └── disclosure_links.py
    ├── portfolio/             # 여러 증권의 결정적 사실 집계
    │   ├── summary.py         # 보장금 합계·실손/중복·손해보험 별도 집계
    │   ├── premium.py         # 보험료 집계
    │   └── demographics.py    # 포트폴리오 단위 인구정보 판정
    ├── evidence/
    │   └── catalog.py         # 분석/Q&A 공용 근거 카탈로그·안전 필터
    ├── analysis/
    │   └── summary_overview.py # 포트폴리오 총평 LLM 생성·검증
    ├── qa/
    │   ├── service.py         # POST /qa/stream use case
    │   ├── planning.py        # 맥락 지시어·복합 질문·도메인 범위 planner
    │   ├── generation.py      # Q&A LLM 생성/streaming
    │   └── claim_channels.py  # 청구 채널 결정적 안내
    ├── reference/
    │   └── premium_benchmark.py # 출처가 있는 보험료 부담 가이드 조회
    └── rag/                   # 공식 약관/제도 RAG + 업로드 세션 RAG
```

의존 방향은 `routes -> policy/portfolio/qa`, `portfolio route -> analysis/summary_overview`, `qa -> portfolio/evidence/coverage_knowledge/rag/llm`, `portfolio -> policy models/coverage_knowledge`, `policy -> llm/grounding/rag` 순서다. 분석 총평과 Q&A는 서버에서만 생성하고, 공통 판단은 `portfolio`, `evidence`, `coverage_knowledge`로 내려서 공유한다.

참조 데이터 로딩·RAG 테이블·migration 경계는 [REFERENCE_DATA.md](REFERENCE_DATA.md)를 따른다. 운영 갱신 대상은 production에서 오래된 JSON으로 조용히 fallback하지 않으며, 실패 정책에 따라 오류나 확인 불가 응답으로 드러낸다.

전역 원칙(내 편·판매원 아님, grounding)은 [../AGENTS.md](../AGENTS.md)에 있고, 아래는 백엔드에서 그걸 강제하는 규칙이다.

- **특정 보험사·상품 전용 로직 금지.** 코드에 보험사/상품 이름이 등장하면 안 된다. 회사별 차이는 일반 로직(형태 검증, 레이아웃 무관 패턴) + 데이터 파일(`services/data/*.json`)로만 흡수한다. `test_no_insurer_specific_identifiers_in_module`이 이를 강제한다.
- **규칙에 매직넘버 금지.** 분류·판정 규칙은 "용어 존재 여부" 같은 이진 판단만 쓴다. 점수·가중치·임계값이 필요해지는 순간, 그건 규칙이 아니라 LLM fallback으로 보낸다.
- **판매·권유를 생성하지 않는다.** 분석·상담·Q&A 생성(LLM 포함)은 상품 가입 권유나 금액 상향 압박을 출력하지 않는다. 금액 검토는 "적정하다/부족하다"는 단정 대신 "확인해볼 질문"으로 제시한다. (루트 "내 편, 판매원 아님" 원칙의 강제)
- **근거 수준을 응답 구조로 드러낸다.** 확정 판단 대신 확인된 사실 / 일반 가이드 / 확인 불가를 구분한다(예: Q&A 섹션의 `basis`, 금액 검토의 `confidence`). 근거 없이 단정하는 필드를 새로 만들지 않는다. (루트 grounding 원칙의 강제)
- **LLM 프롬프트는 별도 기준을 따른다.** 프롬프트 작성, 코드 내 유지/파일 분리 기준, 평가 방식은 [PROMPTING.md](PROMPTING.md)를 먼저 확인한다.

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
