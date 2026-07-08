# Coverly — 프로젝트 가이드

> 이 파일(`AGENTS.md`)이 원본이고 `CLAUDE.md`는 이 파일을 가리키는 symlink다.
> Codex는 `AGENTS.md`, Claude Code는 `CLAUDE.md`를 읽는다 — 하나의 원본, 두 도구.
> 이 문서는 **목차**다. 세부는 각 앱의 `AGENTS.md`에 위임한다.

## 프로젝트 소개

Coverly는 보험 증권(PDF)을 업로드하면 보장을 구조화하고, 부족/중복을 진단하고, 사용자의 보장 질문에 근거 기반으로 답하는 제품이다. 초기 구조는 프론트엔드와 백엔드를 같은 레포에 두되 별도 런타임으로 실행한다.

## 핵심 원칙

- **Grounding (cite-or-refuse)**: 보장 판단·용어 설명은 검색된 약관/사용자 데이터에 근거해야 하며, 근거가 없으면 확인할 수 없다고 답한다.
- **PII 마스킹**: 개인정보는 저장·로그·파일 기록 직전에 반드시 마스킹한다.
- **기계적 강제 > 문서**: 규칙은 formatter, linter, typecheck, test, CI로 강제한다.
- **작은 변경**: 한 작업은 리뷰 가능한 크기로 유지한다.
- **단일 정보원**: 설계·결정은 코드 옆 문서에 남긴다.

## Development Commands

```bash
# 백엔드 (FastAPI, uv)
cd backend && uv run uvicorn app.main:app --reload
uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest

# 프론트엔드 (Next.js, pnpm)
cd frontend && pnpm dev
pnpm lint && pnpm typecheck && pnpm format:check && pnpm build
```

## Project Structure

- **`frontend/`** — Next.js App Router + TypeScript + Tailwind. → [frontend/AGENTS.md](frontend/AGENTS.md)
- **`backend/`** — FastAPI + uv. → [backend/AGENTS.md](backend/AGENTS.md)
- **`.github/`** — GitHub Actions CI + PR 템플릿.

## Language Convention

모든 마크다운(`.md`)은 **한국어**로 작성한다. 코드 코멘트·docstring은 **영어**로 유지한다. 커밋 메시지는 **영어**. 예외로 한국어를 쓰는 것: 사용자 대상 UI 카피와 의도된 데이터 값. 링크 경로·코드블록·frontmatter 키·파일명은 그대로 둔다.

## Commit & Pull Request Guidelines

- **커밋 메시지**: 영어. 명령형 요약 한 줄.
- **PR 제목**: 영어로 작성한다. 예: `chore: scaffold Coverly apps and CI`
- **PR 본문**: 한국어로 작성해도 된다. 요약 · 변경사항 · 결정 및 고민 · 검증 · 후속/범위 밖을 포함한다.
- 혼자 개발하는 동안에는 `main` 직접 커밋을 기본으로 하고, 큰 변경이나 리뷰가 필요한 경우에만 브랜치/PR을 사용한다.

