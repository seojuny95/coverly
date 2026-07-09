# frontend — 프로젝트 가이드

Next.js App Router + TypeScript 프론트엔드. 전체 프로젝트 가이드: [../AGENTS.md](../AGENTS.md).

> `CLAUDE.md`는 이 파일을 가리키는 symlink다.

> **Next.js 16** — API·컨벤션이 자주 바뀐다. 코드 작성 전 공식 문서 또는 설치된 타입/소스에서 해당 API를 확인한다.

## 프로젝트 소개

Coverly의 사용자 인터페이스를 담당한다. 현재는 스캐폴딩 단계이므로 기본 랜딩 화면만 제공한다.

## Development Commands

```bash
pnpm install
pnpm dev
pnpm test && pnpm lint && pnpm typecheck && pnpm format:check && pnpm build
pnpm format
```

## Project Structure

```text
src/
└── app/
    ├── globals.css
    ├── layout.tsx
    └── page.tsx
```

## Coding Style & Naming Conventions

- 포맷은 **Prettier**(+ tailwindcss 플러그인), 린팅은 **ESLint**에 위임한다.
- 기본은 **Server Components**; 상호작용이 필요할 때만 `"use client"`를 사용한다.
- 파일명은 kebab-case, 컴포넌트는 PascalCase를 사용한다.
- 마크다운은 한국어, 코드 코멘트는 영어. 사용자 대상 UI 카피는 한국어.
- 사용자 대상 UI 카피를 작성하거나 수정할 때는 [UX_COPY.md](UX_COPY.md)를 먼저 확인한다.

## Testing Guidelines

- 테스트는 **Vitest + Testing Library**를 사용한다.
- 최소 검증은 `pnpm test`, `pnpm lint`, `pnpm typecheck`, `pnpm format:check`, `pnpm build` 통과다.

## Configuration

- Vercel 배포 시 Root Directory는 `frontend/`로 둔다.
- 클라이언트로 노출되는 환경변수는 `NEXT_PUBLIC_*`만 사용한다.
