# frontend — 프로젝트 가이드

Next.js App Router + TypeScript 프론트엔드. 전체 프로젝트 가이드: [../AGENTS.md](../AGENTS.md).

> `CLAUDE.md`는 이 파일을 가리키는 symlink다.

> **Next.js 16** — API·컨벤션이 자주 바뀐다. 코드 작성 전 공식 문서 또는 설치된 타입/소스에서 해당 API를 확인한다.

## 프로젝트 소개

Coverly의 사용자 인터페이스를 담당한다. 랜딩(`/`) → 업로드(`/upload`) → 분석(`/analysis`) 흐름으로, 보험증권 PDF를 올리면 AI가 정리한 보험 종류별 정리·보장금 합계·상담 전 검토·근거 기반 Q&A를 보여준다. "보험을 팔지 않는 내 편 AI 상담사" 인상을 카피와 화면으로 지키는 게 목표다(제품 방향 → [../AGENTS.md](../AGENTS.md), 카피 기준 → [UX_COPY.md](UX_COPY.md)).

## Development Commands

```bash
pnpm install
pnpm dev
pnpm test && pnpm lint && pnpm dead-code && pnpm typecheck && pnpm format:check && pnpm build
pnpm format
```

## Project Structure

라우트는 얇게 유지하고 화면 로직은 `features/`의 기능 폴더로 분리한다.

```text
src/
├── app/                        # App Router 페이지 (얇은 진입점)
│   ├── page.tsx                # 랜딩
│   ├── upload/page.tsx         # 업로드
│   ├── analysis/page.tsx       # 분석 결과
│   ├── preview/analysis/page.tsx # 개발용 분석 화면 미리보기
│   ├── layout.tsx / globals.css
│   └── error.tsx / global-error.tsx / not-found.tsx
├── components/                 # 공용 UI (coverly-brand, app-error-fallback)
└── features/
    ├── insurance-upload/       # 업로드 폼 + upload-insurance API
    ├── insurance-analysis/     # 분석 페이지, 보장 목록, 인메모리 데이터 Context, 이탈 경고, 보험사 로고
    └── portfolio/              # 보장금 합계, 전체 보험 점검, 청구 안내, Q&A, portfolio API
```

- 증권·분석 데이터는 `insurance-analysis-store.tsx`의 인메모리 React Context(`InsuranceDataProvider`)가 관리한다(업로드 → 분석 전달). 로그인이 없고 민감정보라 **영속 저장은 하지 않는다** — 새로고침·화면 이탈 시 사라지며, 그 전에 경고한다.
- 서버 데이터 패칭은 **react-query**로 통일한다(조회는 `useQuery`, 생성/전송은 `useMutation`). 앱 전역 `QueryClientProvider`는 `app/providers.tsx`에 둔다. 캐시는 인메모리 전용(persister 없음)이라 서비스 탭 전환에는 유지되고 새로고침에는 사라진다.
- 백엔드 호출 함수는 `features/*/*-api.ts`에 모으고, base URL은 `NEXT_PUBLIC_API_BASE_URL`을 쓴다.
- `portfolio-analysis-panel.tsx`는 상태 분기와 섹션 조합만 담당한다. 전체 총평·권장보험·보험료는 `portfolio-overview.tsx`, 손해보험은 `special-policy-sections.tsx`, 청구 안내는 `portfolio-claim-guide.tsx`, 로딩·빈 상태는 `portfolio-analysis-states.tsx`에 둔다.

## Coding Style & Naming Conventions

- 포맷은 **Prettier**(+ tailwindcss 플러그인), 린팅은 **ESLint**에 위임한다.
- **가독성 (한눈에 흐름이 잡히게)**: 컴포넌트는 훑기만 해도 흐름이 보이게 쓴다.
  - 깊은 삼항·중첩 대신 이른 반환(early return)과 이름 있는 헬퍼·하위 컴포넌트로 편다.
  - 상태 계산 → 파생 값 → JSX 순서로 두고, 그 사이를 빈 줄로 나눈다.
  - JSX도 논리 블록마다 줄바꿈으로 구분한다.
- 기본은 **Server Components**; 상호작용이 필요할 때만 `"use client"`를 사용한다.
- 파일명은 kebab-case, 컴포넌트는 PascalCase를 사용한다.
- 마크다운은 한국어, 코드 코멘트는 영어. 사용자 대상 UI 카피는 한국어.
- 사용자 대상 UI 카피를 작성하거나 수정할 때는 [UX_COPY.md](UX_COPY.md)를 먼저 확인한다.

## Testing Guidelines

- 테스트는 **Vitest + Testing Library**를 사용한다.
- 최소 검증은 `pnpm test`, `pnpm lint`, `pnpm dead-code`, `pnpm typecheck`, `pnpm format:check`, `pnpm build` 통과다.

## Configuration

- Vercel 배포 시 Root Directory는 `frontend/`로 둔다.
- 클라이언트로 노출되는 환경변수는 `NEXT_PUBLIC_*`만 사용한다.
