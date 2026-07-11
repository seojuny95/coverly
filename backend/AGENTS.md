# backend — 프로젝트 가이드

FastAPI + uv 백엔드. 전체 프로젝트 가이드: [../AGENTS.md](../AGENTS.md).

> `CLAUDE.md`는 이 파일을 가리키는 symlink다.

## 프로젝트 소개

보험 증권 처리, 보장 구조화, 진단, 약관 기반 Q&A를 담당할 백엔드 앱이다. 현재 `POST /policies/parse` 하나가 전체 파이프라인(파싱 → 분류 → 기본정보 → 보장 추출)을 처리한다.

## Development Commands

```bash
uv sync
uv run uvicorn app.main:app --reload
uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest
```

## Project Structure

`app/services/`는 도메인이 아니라 **파이프라인 단계 = 파일**로 나눈다.

```text
app/
├── main.py              # FastAPI app
├── errors.py            # ApiError, request-id 미들웨어
├── routes/policies.py   # 얇은 라우트: HTTP 관심사만 (검증 → run_pipeline → 응답)
└── services/
    ├── types.py         # ParsedDocument, Coverage, PolicySummary 등 도메인 타입
    ├── parsing.py       # pdfplumber 1회 파싱 → ParsedDocument
    ├── classification.py# 보험종류 분류 (공식 종목 매핑 + LLM fallback)
    ├── summary.py       # 기본정보 (regex 로컬 + LLM 보완)
    ├── grounding.py     # 금액·문구 anti-hallucination (공유)
    ├── coverage.py      # 담보 추출 (표 선택 → LLM 정규화 → grounding)
    ├── explain.py       # 보장내용 없는 담보의 일반 해설
    ├── pipeline.py      # 오케스트레이터: parse → classify+summary → coverage
    ├── llm.py           # OpenAI 경계
    └── data/            # insurer_catalog.json, classification_rules.json
```

## 도메인 규칙

- **특정 보험사·상품 전용 로직 금지.** 코드에 보험사/상품 이름이 등장하면 안 된다. 회사별 차이는 일반 로직(형태 검증, 레이아웃 무관 패턴) + 데이터 파일(`services/data/*.json`)로만 흡수한다. `test_no_insurer_specific_identifiers_in_module`이 이를 강제한다.
- **규칙에 매직넘버 금지.** 분류·판정 규칙은 "용어 존재 여부" 같은 이진 판단만 쓴다. 점수·가중치·임계값이 필요해지는 순간, 그건 규칙이 아니라 LLM fallback으로 보낸다.

## Coding Style & Naming Conventions

- 스타일은 **ruff**에 위임하되, ruff format 통과는 최소선이지 목표가 아니다.
- **가독성**: 중첩 컴프리헨션 지양(풀어서 루프로), 의미 단위로 빈 줄을 나누고, 이름은 하는 일을 그대로 드러낸다.
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

