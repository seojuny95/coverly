# Coverly

보험 증권을 AI로 읽어 보장 내용을 구조화하고, 근거 기반 답변을 제공하는 AI 보험 분석 애플리케이션이다.

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

커밋 전 백엔드와 프론트엔드 포맷/린트 훅을 사용하려면 다음을 한 번 실행한다.

```bash
pre-commit install
```

```bash
cd backend
uv run ruff check .
uv run ruff format --check .
uv run vulture app --min-confidence 80
uv run mypy .
uv run pytest
```

```bash
cd frontend
pnpm test
pnpm lint
pnpm dead-code
pnpm typecheck
pnpm format:check
pnpm build
```
