# backend — 프로젝트 가이드

FastAPI + uv 백엔드. 전체 프로젝트 가이드: [../AGENTS.md](../AGENTS.md).

> `CLAUDE.md`는 이 파일을 가리키는 symlink다.

## 프로젝트 소개

보험 증권 처리, 보장 구조화, 진단, 약관 기반 Q&A를 담당할 백엔드 앱이다. 현재는 스캐폴딩 단계이므로 헬스체크 API만 제공한다.

## Development Commands

```bash
uv sync
uv run uvicorn app.main:app --reload
uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest
```

## Project Structure

```text
app/
└── main.py        # FastAPI app
tests/
└── test_health.py
```

## Coding Style & Naming Conventions

- 스타일은 **ruff**에 위임한다.
- 타입은 **mypy strict**를 통과해야 한다.
- 라우트는 얇게 유지하고, 이후 외부 I/O와 도메인 로직은 `services/` 아래로 분리한다.
- 마크다운은 한국어, 코드 코멘트·docstring은 영어.

## Testing Guidelines

- 테스트는 **pytest**를 사용한다.
- 파일명은 `test_<module>.py` 형식을 따른다.
- 변경 후 `ruff check`, `ruff format --check`, `mypy`, `pytest`를 모두 통과시킨다.

## Configuration

- Python 버전은 `.python-version`의 3.12를 따른다.
- 시크릿과 실제 증권 원본은 커밋하지 않는다.

