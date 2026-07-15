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

백엔드는 `app/core`, `app/modules`, `app/rag`, `app/integrations`로 나눈다. `app`는 런타임 코드만 담고, `backend/evals`는 평가 전용이다. `app`는 `backend/evals`를 import하지 않는다.

```text
app/
├── main.py                  # FastAPI 앱 조립
├── core/                    # config, lifespan, errors, middleware, 공유 pure helper
├── modules/
│   ├── policy/              # 증권 파싱·분류·요약·담보 해설
│   ├── portfolio/           # 다건 증권 집계와 총평 입력 준비
│   ├── analysis/            # 포트폴리오 총평 생성
│   ├── qa/                  # 근거 기반 Q&A
│   ├── coverage/            # 담보 분류·매칭·설명
│   ├── evidence/            # 분석/Q&A 공용 근거 카탈로그
│   └── reference_data/      # DB-backed reference data access
├── rag/                     # 공유 런타임 RAG subsystem
│   ├── official/            # 공식 약관·제도 RAG
│   └── policy/              # 업로드 세션 RAG
└── integrations/
    ├── openai/              # OpenAI client boundary
    └── postgres/            # pgvector / Postgres 구현

backend/evals/
└── rag/
    ├── official/            # official retrieval/generation eval runners + datasets
    └── policy/              # policy retrieval/generation eval runners + datasets

tests/
├── core/                    # 앱 조립, 미들웨어, 공용 규칙 테스트
├── modules/                 # policy, portfolio, qa 등 기능별 테스트
├── rag/                     # official / policy 런타임 RAG 테스트
├── evals/                   # 평가 runner와 metric 테스트
└── integrations/            # Postgres 등 외부 연동 구현 테스트
```

FastAPI 라우터는 기능 모듈 가까이에 둔다. `APIRouter`는 모듈별 엔드포인트 묶음에만 쓰고, `Depends`는 실제로 필요한 경우에만 라우터/핸들러에서 국소적으로 사용한다. 전역 의존성 주입은 기본 패턴이 아니며, 앱 수명 주기 연결은 `lifespan`으로 처리한다. `lifespan`은 공용 캐시 워밍, 초기화, 종료 정리에 사용하고 `create_app()`에서 연결한다.

의존 방향은 대체로 `modules -> core/integrations/rag`, `rag -> integrations/core`, `integrations -> 외부 시스템`이다. `analysis`와 `qa`는 서버 응답을 생성하는 계층이고, `coverage`, `evidence`, `reference_data`는 여러 기능이 공유하는 순수/조회 로직을 담는다. `app`는 평가 코드를 참조하지 않는다.

참조 데이터와 RAG 테이블 경계, Supabase migration을 포함한 DB 원본 정의는 [REFERENCE_DATA.md](REFERENCE_DATA.md)를 따른다. 운영 갱신 대상은 production에서 오래된 JSON으로 조용히 fallback하지 않으며, 실패 정책에 따라 오류나 확인 불가 응답으로 드러낸다.

전역 원칙(내 편·판매원 아님, grounding)은 [../AGENTS.md](../AGENTS.md)에 있고, 아래는 백엔드에서 그걸 강제하는 규칙이다.

- **특정 보험사·상품 전용 로직 금지.** 코드에 보험사/상품 이름이 등장하면 안 된다. 회사별 차이는 일반 로직 + 참조 데이터만으로 흡수한다.
- **규칙에 매직넘버 금지.** 분류·판정 규칙은 "용어 존재 여부" 같은 이진 판단만 쓴다. 점수·가중치·임계값이 필요해지는 순간, 그건 규칙이 아니라 LLM fallback으로 보낸다.
- **판매·권유를 생성하지 않는다.** 분석·상담·Q&A 생성(LLM 포함)은 상품 가입 권유나 금액 상향 압박을 출력하지 않는다. 금액 검토는 "적정하다/부족하다"는 단정 대신 "확인해볼 질문"으로 제시한다. (루트 "내 편, 판매원 아님" 원칙의 강제)
- **근거 수준을 응답 구조로 드러낸다.** 확정 판단 대신 확인된 사실 / 일반 가이드 / 확인 불가를 구분한다(예: Q&A 섹션의 `basis`, 금액 검토의 `confidence`). 근거 없이 단정하는 필드를 새로 만들지 않는다. (루트 grounding 원칙의 강제)
- **LLM 프롬프트는 별도 기준을 따른다.** 프롬프트 작성, 코드 내 유지/파일 분리 기준, 평가 방식은 [PROMPTING.md](PROMPTING.md)를 먼저 확인한다.

- **평가와 런타임을 분리한다.** `backend/evals`는 품질 측정 전용이고, `tests/`는 correctness를 검증한다. `app`는 `evals`를 import하지 않는다.

## Review Guidelines

백엔드 리뷰는 FastAPI 앱이 기능별 모듈 경계와 데이터 소유권을 지키는지 우선 확인한다.

- **라우터는 얇은가**: `APIRouter`는 요청/응답 조립만 담당하고, 파싱·분류·집계·LLM 호출·DB 조회 로직은 `modules/`, `rag/`, `integrations/`로 내려가야 한다.
- **의존성 경계가 맞는가**: `modules`가 외부 시스템 구현에 직접 달라붙지 않고 `integrations`나 명확한 repository/helper 경계를 거치는지 본다. `app`가 `backend/evals`를 import하면 안 된다.
- **FastAPI 관용 방식인가**: 공유 자원 초기화는 `lifespan`, 기능별 라우팅은 `APIRouter`, 요청 단위 의존성은 필요한 경우 `Depends`로 표현한다. 전역 싱글톤이나 import-time side effect로 우회하지 않는다.
- **참조 데이터 소유권이 맞는가**: Supabase 소유 데이터(`REFERENCE_DATA.md`)를 코드 상수·bundled JSON·silent fallback으로 복제하지 않는다. 코드 소유 규칙과 DB 소유 사실을 섞지 않는다.
- **하드코딩이 정당한가**: 보험사/상품 전용 분기, 출처 없는 기준금액, 임의 score/weight/threshold가 들어오면 거절한다. 필요한 운영 데이터는 DB나 명시된 참조 데이터로 옮긴다.
- **LLM 경계가 안전한가**: 프롬프트, grounding, cite-or-refuse, fallback 정책이 [PROMPTING.md](PROMPTING.md)와 루트 원칙을 따른다. 근거 없는 총평이나 보장 단정은 허용하지 않는다.
- **실패 정책이 명확한가**: DB, RAG, LLM, 외부 API 실패가 조용히 성공처럼 보이지 않아야 한다. 전체 분석을 실패시켜야 하는 참조 데이터 오류와 확인 불가로 degrade할 수 있는 검색 오류를 구분한다.
- **타입과 테스트가 회귀를 막는가**: Pydantic schema, mypy, pytest fixture가 실제 응답 계약을 반영하는지 본다. LLM/API/DB는 유닛 테스트에서 stub 가능해야 한다.
- **성능·비용이 예측 가능한가**: 불필요한 LLM 호출, 반복 DB 조회, 대용량 PDF/RAG 처리의 중복 작업이 없는지 확인한다. 캐시는 소유권과 무효화 기준이 명확해야 한다.

## Coding Style & Naming Conventions

- 스타일은 **ruff**에 위임하되, ruff format 통과는 최소선이지 목표가 아니다.
- **가독성 (한눈에 흐름이 잡히게)**: 코드는 훑기만 해도 흐름과 로직이 보여야 한다.
  - 중첩 컴프리헨션·깊은 중첩은 풀어서 루프와 이른 반환(early return)으로 편다.
  - 처리 단계(입력 검증 → 변환 → 출력)마다 빈 줄로 문단을 나눈다.
  - 들여쓰기가 3단을 넘으면 함수를 쪼갠다.
  - 이름은 하는 일을 그대로 드러낸다.
- 타입은 **mypy strict**를 통과해야 한다.
- 라우트는 얇게 유지하고, 외부 I/O와 도메인 로직은 해당 `modules/`, `rag/`, `integrations/` 아래로 분리한다.
- 마크다운은 한국어, 코드 코멘트·docstring은 영어. 한국어 필드명(담보명 등)은 의도된 데이터 값이다.

## 테스트 정책

- 테스트는 **pytest**, 파일명은 `test_<module>.py`.
- 테스트 폴더는 런타임 책임 구조를 따라 `core`, `modules`, `rag`, `integrations`로 나누고, 평가 코드 테스트는 `tests/evals`에 둔다.
- 변경 후 `ruff check`, `ruff format --check`, `mypy`, `pytest`를 모두 통과시킨다.
- **mock 문서는 정확한 추출값을 단언**하고, 실제 샘플(`test_local_*`, gitignored PDF)은 골든 필드 + 불변식(grounding·degrade·응답 shape)을 검증한다.
- **LLM 비용 관리**: 반복(iteration) 중에는 비-LLM 테스트만 돌리고, LLM 의존 테스트(`test_local_*`)는 작업 마무리에 1회만 실행한다.
- **유닛 테스트가 실제 API를 호출하면 안 된다.** LLM 경계는 주입 가능한 completer로 설계하고, 유닛 테스트에서는 stub을 주입한다(예: `test_summary.py`의 autouse fixture). 환경에 `OPENAI_API_KEY`가 있어도 유닛 테스트는 결정적이어야 한다.

## Configuration

- Python 버전은 `.python-version`의 3.12를 따른다.
- 시크릿과 실제 증권 원본은 커밋하지 않는다.
