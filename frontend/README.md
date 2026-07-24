# Coverly AI frontend

Next.js App Router 기반 프론트엔드 앱이다.

## 실행

```bash
pnpm install
pnpm dev
```

기본 백엔드 주소는 `http://localhost:8000`이다. 다른 주소를 사용하면
`NEXT_PUBLIC_API_BASE_URL`을 설정한다. 포트폴리오당 PDF는 최대 5개까지 선택할 수
있으며, 한도는 백엔드 OpenAPI 계약에서 생성된 상수를 사용한다.

React Compiler는 `next.config.ts`의 `reactCompiler: true`로 활성화되어 있다.

## 검증

```bash
pnpm api:check
pnpm test
pnpm lint
pnpm typecheck
pnpm format:check
pnpm build
```
