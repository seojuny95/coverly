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
pnpm test && pnpm lint && pnpm typecheck && pnpm format:check && pnpm build
pnpm format
```

## Project Structure

라우트는 얇게 유지하고 화면 로직은 `features/`의 기능 폴더로 분리한다.

```text
src/
├── app/                         # App Router 페이지 (얇은 진입점)
│   ├── page.tsx                 # 랜딩
│   ├── upload/page.tsx          # 업로드
│   ├── analysis/page.tsx        # 분석 결과
│   ├── layout.tsx / globals.css
│   └── error.tsx / global-error.tsx / not-found.tsx
├── features/
│   ├── upload/                  # 업로드 폼, 진행 화면, 업로드 API
│   └── analysis/                # 분석 화면, 세션, 인메모리 상태, 이탈 경고
│       └── portfolio/           # 보장 합계, 상담 전 검토, Q&A
├── shared/
│   └── components/              # 앱 전역 공용 UI
└── test/                         # 전역 테스트 설정과 공용 테스트 helper
```

- 화면에 표시하는 증권·분석 데이터와 `portfolioSessionToken`은 `features/analysis/store.tsx`의 인메모리 React Context(`InsuranceDataProvider`)가 관리한다(업로드 → 분석 전달). 브라우저의 localStorage, sessionStorage, IndexedDB에는 저장하지 않으므로 새로고침·화면 이탈 시 사라지며, 그 전에 경고한다.
- 업로드가 시작되면 프론트엔드는 포트폴리오 세션 토큰 하나를 만들고 이후 업로드·분석·Q&A에 재사용한다. 분석과 Q&A 요청에는 모든 증권을 반복 전송하지 않고 토큰과 필요한 문서 ID만 보낸다. PII를 최소화한 구조화 증권과 분석 캐시는 서버가 Supabase `private` 스키마에 만료 시각까지 임시 저장하며, 토큰 삭제 시 함께 정리한다.
- 서버 데이터 패칭은 **react-query**로 통일한다(조회는 `useQuery`, 생성/전송은 `useMutation`). 앱 전역 `QueryClientProvider`는 `app/providers.tsx`에 둔다. 캐시는 인메모리 전용(persister 없음)이라 서비스 탭 전환에는 유지되고 새로고침에는 사라진다.
- 백엔드 호출 함수는 사용하는 기능 폴더의 `api.ts` 또는 목적이 드러나는 `*-api.ts`에 모으고, base URL은 `NEXT_PUBLIC_API_BASE_URL`을 쓴다.

## Review Guidelines

프론트엔드 리뷰는 UI가 서버 사실을 왜곡하지 않고, Next.js/React 경계를 지키는지 우선 확인한다.

- **서버 사실을 만들지 않는가**: 분석 총평, 보장 판단, 기준금액, 출처를 프론트에서 synthetic fallback으로 생성하지 않는다. 서버가 실패하면 재시도/오류/미확인을 보여준다.
- **컴포넌트 경계가 명확한가**: route file은 얇게 유지하고, 화면 상태·API 호출·표시 로직은 `features/` 안에서 기능별로 나눈다. 너무 큰 컴포넌트는 하위 컴포넌트와 helper로 분리한다.
- **공통 경계를 놓치지 않는가**: 둘 이상의 화면이나 기능에서 재사용할 수 있는 UI와 hook을 각 사용처에 복제하지 않는다. 앱 전체에서 쓰는 UI는 `shared/components/`에 두고, 한 기능 안에서만 공유하면 해당 `features/*/` 안의 공통 컴포넌트나 hook으로 둔다. 이름만 공통인 억지 추상화는 만들지 않되, 같은 동작·접근성·스타일 규칙의 중복은 공통 경계로 올린다.
- **코드 길이가 책임 혼합을 드러내지 않는가**: 파일이나 컴포넌트가 길어지는 것은 로직과 UI 책임을 분리해야 한다는 신호로 본다. 줄 수 자체를 목표로 삼지는 않지만, 서로 독립적으로 이름 붙일 수 있는 상태 관리·파생 계산·화면 섹션이 한 파일에 쌓이면 hook, helper, 하위 컴포넌트로 분리한다.
- **Next.js/React 관용 방식인가**: 기본은 Server Components이고, 상호작용·브라우저 API·client state가 필요한 파일에만 `"use client"`를 둔다. 불필요한 client boundary를 만들지 않는다.
- **react-query 사용이 일관적인가**: 서버 조회는 `useQuery`, 생성·전송은 `useMutation`을 사용한다. 임의 fetch state, 중복 캐시, 영속 저장으로 민감정보를 남기지 않는다.
- **API 계약이 타입으로 드러나는가**: backend 응답 shape 변경은 `*-api.ts` 타입, fixture, 화면 테스트에 함께 반영한다. `any`나 optional 남발로 계약 깨짐을 숨기지 않는다.
- **민감정보를 저장하지 않는가**: 보험증권 원문, 분석 결과, 피보험자 정보, 계약번호, 상담 내용은 localStorage/sessionStorage/IndexedDB/persisted query cache에 저장하지 않는다. 브라우저는 인메모리 상태와 짧은 세션 토큰만 유지하고, 로그·analytics·error reporting에도 원문 데이터를 보내지 않는다. 서버의 임시 저장 범위와 마스킹·만료 규칙은 [../backend/REFERENCE_DATA.md](../backend/REFERENCE_DATA.md)를 따른다.
- **클라이언트 노출 경계가 안전한가**: 브라우저 번들에는 `NEXT_PUBLIC_*`로 공개해도 되는 값만 들어가야 한다. API key, service role key, DB URL, 내부 endpoint는 프론트 코드·테스트 fixture·환경 예시에 넣지 않는다.
- **UX 카피 원칙을 지키는가**: 공포·판매 압박·가입 권유 카피를 넣지 않는다. 사용자 대상 문구는 [UX_COPY.md](UX_COPY.md)를 따른다.
- **하드코딩이 정당한가**: 출처, 기준금액, 보험 판단, 보험사별 분기를 UI 코드에 박지 않는다. 표시용 label·정적 설명은 가능하지만 서버 데이터와 충돌하면 서버를 우선한다.
- **접근성과 안전한 링크를 지키는가**: 버튼/링크의 의미, heading 구조, keyboard interaction, `safeHref` 같은 URL 방어를 확인한다. 서버가 준 URL·markdown·HTML은 신뢰하지 말고 허용된 프로토콜/렌더링 경로만 사용한다.
- **렌더링 비용이 과하지 않은가**: 큰 리스트·계산·애니메이션이 불필요하게 매 렌더마다 반복되지 않는지 본다. 다만 성능 최적화 hook은 실제 병목과 팀 패턴이 있을 때만 추가한다.
- **테스트가 사용자 관점인가**: Testing Library 테스트는 구현 세부보다 사용자가 보는 문구, 상태 전환, 링크, 오류 표시를 검증한다.

## Coding Style & Naming Conventions

- 포맷은 **Prettier**(+ tailwindcss 플러그인), 린팅은 **ESLint**에 위임한다.
- **가독성 (한눈에 흐름이 잡히게)**: 컴포넌트는 훑기만 해도 흐름이 보이게 쓴다.
  - 깊은 삼항·중첩 대신 이른 반환(early return)과 이름 있는 헬퍼·하위 컴포넌트로 편다.
  - 상태 계산 → 파생 값 → JSX 순서로 두고, 그 사이를 빈 줄로 나눈다.
  - JSX도 논리 블록마다 줄바꿈으로 구분한다.
- **가독성을 기능과 동등한 완료 조건으로 본다**: 동작하더라도 이름과 파일 구조만으로 의도가 드러나지 않거나, 한 번에 읽기 어려운 흐름은 완료된 코드로 보지 않는다. 긴 함수·컴포넌트는 책임을 이름 붙일 수 있는 단위로 나누고, 호출부에서 전체 흐름이 보이게 한다.
- **주석은 이유와 제약만 남긴다**: 코드를 그대로 풀어쓴 설명, 임시 작업 과정, 작성자만 이해할 메모, 실제로 유지보수자가 읽지 않을 서술형 주석은 작성하지 않는다. 이런 주석이나 코드와 맞지 않는 낡은 주석을 발견하면 제거한다. 코드만으로 드러나지 않는 의사결정·안전 제약·프레임워크 우회 이유만 짧게 영어로 남긴다.
- 기본은 **Server Components**; 상호작용이 필요할 때만 `"use client"`를 사용한다.
- 파일명은 kebab-case, 컴포넌트는 PascalCase를 사용한다.
- 기능 폴더가 문맥을 제공하므로 하위 파일명에 같은 기능명을 prefix로 반복하지 않는다. 예: `features/upload/form.tsx`, `features/analysis/store.tsx`, `features/analysis/portfolio/panel.tsx`.
- 파일명은 폴더 안에서 간결하게 유지하되 export 이름은 import 문맥과 React DevTools에서 의미가 드러나게 짓는다. 예: `form.tsx`의 `InsuranceUploadForm`, `panel.tsx`의 `PortfolioAnalysisPanel`.
- 마크다운은 한국어, 코드 코멘트는 영어. 사용자 대상 UI 카피는 한국어.
- 사용자 대상 UI 카피를 작성하거나 수정할 때는 [UX_COPY.md](UX_COPY.md)를 먼저 확인한다.

## Testing Guidelines

- 테스트는 **Vitest + Testing Library**를 사용한다.
- 기능 테스트는 구현 파일 옆에 `*.test.ts(x)`로 두고, 전역 설정과 여러 기능에서 재사용하는 테스트 helper만 `test/`에 둔다.
- 최소 검증은 `pnpm test`, `pnpm lint`, `pnpm typecheck`, `pnpm format:check`, `pnpm build` 통과다.
- 작업 완료 전 변경 범위와 인접 코드를 다시 검색해 중복 코드, 불필요한 코드, 도달할 수 없는 dead code, 미사용 import·export, 참조되지 않는 파일이 없는지 확인한다. 발견한 항목은 삭제하거나, 의도적으로 남겨야 한다면 코드에서 그 이유가 드러나게 한다. 이 점검과 최소 검증을 모두 마쳐야 작업이 완료된 것으로 본다.

## Configuration

- Vercel 배포 시 Root Directory는 `frontend/`로 둔다.
- 클라이언트로 노출되는 환경변수는 `NEXT_PUBLIC_*`만 사용한다.
