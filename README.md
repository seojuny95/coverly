# Coverly

보험 증권을 읽고, 보장 내용을 구조화하고, 근거 기반 답변을 제공하기 위한 애플리케이션이다.

## 실행

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload
```

```bash
cd frontend
pnpm install
pnpm dev
```

## 검증

```bash
cd backend
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run pytest
```

```bash
cd frontend
pnpm lint
pnpm typecheck
pnpm format:check
pnpm build
```

