# 프론트엔드 로딩·전환 애니메이션 정리 — 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 프론트엔드의 두 갈래 애니메이션 체계를 `tw-animate-css` 하나로 통일하고, 사용자가 지적한 8개 지점의 하드 컷을 없앤다.

**Architecture:** 모션 규칙은 `globals.css`의 `@theme`에 `--animate-*` 토큰으로 한 번만 정의하고, 컴포넌트는 `animate-enter` 같은 이름 하나만 쓴다. `prefers-reduced-motion` 처리는 토큰 정의 안에 넣어 사용처가 신경 쓰지 않게 한다. JS 모션 라이브러리는 도입하지 않으며, 새 `"use client"` 경계도 만들지 않는다.

**Tech Stack:** Next.js 16 App Router, React 19, Tailwind CSS v4, tw-animate-css, Vitest + Testing Library

## Global Constraints

- 작업 디렉터리는 `frontend/`. 패키지 매니저는 **pnpm**.
- 모션 규칙: 진입은 **페이드 + 아래에서 위로 4px, 200ms, ease-out**. 과하게 만들지 않는다.
- 모든 진입 연출과 무한 루프 연출은 `prefers-reduced-motion: reduce`에서 재생되지 않아야 한다.
- 애니메이션 클래스 조합이 두 곳 이상에서 반복되면 `@theme` 토큰으로 올린다. 문자열 복붙 금지.
- 코드 주석은 **영어**, 사용자 대상 UI 카피는 **한국어**. 카피는 `frontend/UX_COPY.md` 기준을 따르고 판매 권유·공포 문구를 쓰지 않는다.
- 파일명은 kebab-case, 컴포넌트는 PascalCase, 기능 폴더명을 파일명에 prefix로 반복하지 않는다.
- 서버가 확인하지 않은 사실을 UI가 단정하지 않는다.
- 각 태스크는 독립적으로 커밋한다. 커밋 메시지는 **영어**, 명령형 한 줄.
- 각 태스크 완료 시 최소 `pnpm test && pnpm lint && pnpm typecheck && pnpm format:check`를 통과해야 한다.

---

## File Structure

| 파일 | 책임 | 변경 |
| --- | --- | --- |
| `src/app/globals.css` | 모션 토큰 정의 + 화면 전용 keyframes. 단일 정보원 | 수정 |
| `src/features/upload/use-completion-beat.ts` | 완료 표시를 잠깐 보여준 뒤 다음 동작으로 넘기는 대기 로직 | **신규** |
| `src/features/upload/progress.tsx` | 로딩 화면 표시. 진행/완료 단계를 prop으로 받음 | 수정 |
| `src/features/upload/use-orchestration.ts` | 업로드 트랜잭션. 완료 비트를 호출부에서 조립 | 수정 |
| `src/features/upload/use-selected-files.ts` | 파일 선택 상태. 암호 검사 중 상태 소유 | 수정 |
| `src/features/upload/types.ts` | `SelectedUploadFile` 타입 | 수정 |
| `src/features/upload/file-list.tsx` | 파일 목록 표시. "확인 중" 배지 | 수정 |
| `src/features/upload/form.tsx` | 폼 조립. 암호 검사 중 제출 잠금 | 수정 |
| `src/features/analysis/screen.tsx` | 탭 패널 래퍼에 진입 연출 | 수정 |
| `src/shared/components/ui/skeleton.tsx` | 스켈레톤 진입 연출의 공통 자리 | 수정 |
| `src/features/analysis/portfolio/total-table.tsx` | 합계 결과 진입 연출 | 수정 |
| `src/features/analysis/portfolio/panel/index.tsx` | 분석 결과 진입 연출 | 수정 |
| `src/features/analysis/portfolio/recommendation-cards/coverage-reference.tsx` | 체크박스 변경 시 양방향 전환 | 수정 |
| `src/app/page.tsx`, `portfolio/panel/portfolio-overview.tsx`, `portfolio/special-policy-sections.tsx`, `portfolio/panel/actual-loss-coverage-review.tsx`, `portfolio/recommendation-cards/index.tsx`, `portfolio/amount-range-meter.tsx` | 커스텀 CSS 클래스 → 유틸리티 클래스 교체 | 수정 |

---

## Task 1: tw-animate-css 설치

`shared/components/ui/`의 dialog·alert-dialog·tooltip과 `portfolio/chatbot.tsx`는 이미 `data-open:animate-in`, `fade-in-0`, `zoom-in-95`, `slide-in-from-bottom-2` 클래스를 쓰고 있으나, 이 유틸리티를 제공하는 패키지가 없어 조용히 무시되고 있다. 패키지를 설치하면 **기존 클래스 문자열을 하나도 고치지 않고** 모달·툴팁·배너 애니메이션이 복구된다.

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/src/app/globals.css:1`

**Interfaces:**
- Consumes: 없음
- Produces: `animate-in` / `animate-out` / `fade-in` / `fade-out` / `slide-in-from-*` / `zoom-in-*` / `duration-*` 유틸리티. 이후 모든 태스크가 사용한다.

- [ ] **Step 1: 패키지 설치**

```bash
cd frontend && pnpm add -D tw-animate-css
```

- [ ] **Step 2: globals.css에서 import**

`src/app/globals.css` 최상단, `@import "tailwindcss";` **바로 다음 줄**에 추가한다. 순서가 중요하다 — Tailwind 이후에 와야 유틸리티가 등록된다.

```css
@import "tailwindcss";
@import "tw-animate-css";
```

- [ ] **Step 3: 유틸리티가 실제로 생성되는지 확인**

```bash
cd frontend && pnpm build
```

Expected: 빌드 성공.

빌드 산출 CSS에 클래스가 들어갔는지 확인한다.

```bash
cd frontend && grep -rlq "animate-in" .next/static/css/ && echo "OK: animate-in utility generated" || echo "FAIL: utility missing"
```

Expected: `OK: animate-in utility generated`

- [ ] **Step 4: 기존 테스트 회귀 확인**

```bash
cd frontend && pnpm test && pnpm lint && pnpm typecheck && pnpm format:check
```

Expected: 전부 통과.

- [ ] **Step 5: 커밋**

```bash
cd frontend && git add package.json pnpm-lock.yaml src/app/globals.css
git commit -m "chore: install tw-animate-css to restore shadcn ui animations"
```

---

## Task 2: 죽은 CSS 제거

`globals.css`에 어디에서도 참조되지 않는 클래스와 keyframes가 있다. 다음 태스크에서 이 파일을 크게 손대기 전에 먼저 걷어내, 이전 작업이 죽은 코드까지 옮기는 일을 막는다.

**Files:**
- Modify: `frontend/src/app/globals.css:103-130, 143-164, 213-236`

**Interfaces:**
- Consumes: 없음
- Produces: 없음 (순수 삭제)

- [ ] **Step 1: 미사용임을 먼저 증명**

```bash
cd frontend && grep -rn "premium-position\|coverage-orbit\|coverage-node\|overview-breathe" src --exclude=globals.css
```

Expected: 출력 없음 (= 어디에서도 사용하지 않음). **출력이 있으면 삭제하지 말고 멈춘 뒤 보고한다.**

- [ ] **Step 2: 죽은 CSS 삭제**

`src/app/globals.css`에서 다음 블록을 모두 제거한다.

- `.analysis-coverage-orbit { ... }`
- `.analysis-coverage-orbit::before { ... }`
- `.analysis-coverage-node { ... }`
- `.analysis-coverage-node:nth-child(2) { ... }`
- `.analysis-coverage-node:nth-child(3) { ... }`
- `.premium-position-user { ... }`
- `@keyframes analysis-overview-breathe { ... }`
- `@keyframes analysis-coverage-node { ... }`
- `@keyframes premium-position-marker { ... }`

`.amount-range-fill`과 `@keyframes amount-range-fill`은 `amount-range-meter.tsx`가 사용하므로 **남긴다.**

- [ ] **Step 3: 검증**

```bash
cd frontend && pnpm test && pnpm lint && pnpm typecheck && pnpm format:check && pnpm build
```

Expected: 전부 통과.

- [ ] **Step 4: 커밋**

```bash
cd frontend && git add src/app/globals.css
git commit -m "chore: remove unreferenced animation css"
```

---

## Task 3: 공통 모션 토큰 정의

진입 규칙을 8개 지점에 클래스 문자열로 복붙하면 규칙이 흩어진다. `@theme`에 이름 하나로 정의하고, 컴포넌트는 그 이름만 쓴다.

**Files:**
- Modify: `frontend/src/app/globals.css` (`@theme` 블록 안, `--radius-4xl` 정의 다음)

**Interfaces:**
- Consumes: Task 1의 tw-animate-css
- Produces:
  - `animate-enter` — 페이드 + 4px 아래에서 위로, 200ms ease-out. 콘텐츠 진입 기본값
  - `animate-enter-overlay` — 페이드만, 300ms ease-out. 전체화면 오버레이용
  - 둘 다 `prefers-reduced-motion: reduce`에서 재생되지 않는다

- [ ] **Step 1: 토큰과 keyframes 추가**

`src/app/globals.css`의 `@theme` 블록 안, `--radius-4xl` 줄 다음에 추가한다.

```css
  /* Shared motion tokens. Every enter animation in the app resolves to one of
     these so the rule lives in one place instead of in class strings. */
  --animate-enter: enter 200ms ease-out both;
  --animate-enter-overlay: enter-overlay 300ms ease-out both;
```

`@theme` 블록을 **닫은 뒤**, 파일의 keyframes 구획에 추가한다.

```css
@keyframes enter {
  from {
    opacity: 0;
    transform: translateY(4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes enter-overlay {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}
```

- [ ] **Step 2: reduced-motion 처리를 토큰 쪽에 넣기**

사용처가 매번 `motion-safe:`를 붙이지 않아도 되도록, 파일 끝에 전역 규칙을 둔다.

```css
/* Motion preference is honored at the token level so call sites can use a
   single class name without repeating a motion-safe: prefix. */
@media (prefers-reduced-motion: reduce) {
  .animate-enter,
  .animate-enter-overlay {
    animation: none;
  }
}
```

- [ ] **Step 3: 토큰이 유틸리티로 생성되는지 확인**

임시로 `src/app/page.tsx`의 최상위 요소에 `animate-enter`를 붙이고 빌드한다.

```bash
cd frontend && pnpm build && grep -rlq "animate-enter" .next/static/css/ && echo "OK: token generated" || echo "FAIL: token missing"
```

Expected: `OK: token generated`

확인 후 임시로 붙인 클래스는 **되돌린다** (실제 적용은 Task 4에서 한다).

- [ ] **Step 4: 검증**

```bash
cd frontend && pnpm test && pnpm lint && pnpm typecheck && pnpm format:check
```

Expected: 전부 통과.

- [ ] **Step 5: 커밋**

```bash
cd frontend && git add src/app/globals.css
git commit -m "feat: add shared enter motion tokens"
```

---

## Task 4: 진입 애니메이션 CSS 클래스를 토큰으로 이전

`.analysis-overview-reveal`, `.analysis-overview-delay-1`, `.analysis-status-message`는 진입 연출이라 Task 3의 토큰으로 대체할 수 있다. 교체하고 원본 CSS를 제거해 체계를 하나로 만든다.

**Files:**
- Modify: `frontend/src/features/analysis/portfolio/panel/portfolio-overview.tsx`
- Modify: `frontend/src/features/analysis/portfolio/special-policy-sections.tsx`
- Modify: `frontend/src/features/analysis/portfolio/panel/actual-loss-coverage-review.tsx`
- Modify: `frontend/src/features/analysis/portfolio/recommendation-cards/index.tsx`
- Modify: `frontend/src/features/upload/progress.tsx:139`
- Modify: `frontend/src/app/globals.css`

**Interfaces:**
- Consumes: Task 3의 `animate-enter`
- Produces: 없음

- [ ] **Step 1: 교체 대상 위치 확인**

```bash
cd frontend && grep -rn "analysis-overview-reveal\|analysis-overview-delay-1\|analysis-status-message" src --exclude=globals.css
```

출력된 모든 위치를 기록한다.

- [ ] **Step 2: 클래스 교체**

각 위치에서 다음과 같이 바꾼다.

- `analysis-overview-reveal` → `animate-enter`
- `analysis-overview-delay-1` → `delay-100` (tw-animate-css의 `delay-*` 유틸리티)
- `analysis-status-message` → `animate-enter`

`progress.tsx:139`의 경우:

```tsx
        <p
          key={statusMessage}
          className="animate-enter mt-6 text-sm leading-6 text-zinc-500"
        >
```

`key={statusMessage}`는 문구가 바뀔 때마다 재마운트시켜 애니메이션을 다시 재생하게 하는 장치이므로 **유지한다.**

- [ ] **Step 3: 원본 CSS 제거**

`src/app/globals.css`에서 다음을 제거한다.

- `.analysis-overview-reveal { ... }`
- `.analysis-overview-delay-1 { ... }`
- `.analysis-status-message { ... }`
- `@keyframes analysis-overview-reveal { ... }`
- `@keyframes analysis-status-fade { ... }`

`.analysis-overview-grid`(배경 격자무늬)는 애니메이션이 아니므로 **남긴다.**

- [ ] **Step 4: 잔여 참조가 없는지 확인**

```bash
cd frontend && grep -rn "analysis-overview-reveal\|analysis-overview-delay-1\|analysis-status-message\|analysis-status-fade" src
```

Expected: 출력 없음.

- [ ] **Step 5: 검증**

```bash
cd frontend && pnpm test && pnpm lint && pnpm typecheck && pnpm format:check && pnpm build
```

Expected: 전부 통과.

- [ ] **Step 6: 커밋**

```bash
cd frontend && git add src/app/globals.css src/features
git commit -m "refactor: replace custom reveal css with shared enter token"
```

---

## Task 5: 화면 전용 keyframes를 @theme 토큰으로 등록

랜딩 히어로의 무한 루프 연출과 업로드 픽셀 로더, 금액 미터는 스텝 타이밍·다중 키프레임에 의존해 유틸리티 조합으로 옮길 수 없다. keyframes 정의는 유지하되 `@theme`에 등록해 **호출부는 다른 곳과 똑같이 `animate-<name>` 클래스만 쓰게** 만든다. 정의는 한 곳에 모이고, 컴포넌트에서 커스텀 CSS 클래스가 사라진다.

**Files:**
- Modify: `frontend/src/app/globals.css`
- Modify: `frontend/src/app/page.tsx`
- Modify: `frontend/src/features/upload/progress.tsx:92`
- Modify: `frontend/src/features/analysis/portfolio/amount-range-meter.tsx`

**Interfaces:**
- Consumes: Task 3의 `@theme` 구획
- Produces: `animate-evidence-scan`, `animate-evidence-signal`, `animate-evidence-glow`, `animate-evidence-result-row`, `animate-evidence-complete`, `animate-pixel-pulse`, `animate-amount-range-fill`

- [ ] **Step 1: @theme에 애니메이션 토큰 등록**

`@theme` 블록의 모션 토큰 구획에, 기존 CSS 클래스가 쓰던 것과 **동일한 duration·timing·iteration**으로 추가한다. 값은 현재 `globals.css`에 적힌 것을 그대로 옮긴다.

```css
  /* Screen-specific animations. Their keyframes cannot be expressed as
     utility combinations (step timing, many keyframes), so only the entry
     point is unified here. */
  --animate-evidence-scan: evidence-scan 8s ease-in-out infinite;
  --animate-evidence-signal: evidence-signal 8s linear infinite;
  --animate-evidence-glow: evidence-glow 8s steps(4, end) infinite;
  --animate-evidence-result-row: evidence-result-row 8s steps(1, end) infinite;
  --animate-evidence-complete: evidence-complete 8s steps(1, end) infinite;
  --animate-pixel-pulse: analysis-pixel-pulse 1.6s steps(2, end) infinite;
  --animate-amount-range-fill: amount-range-fill 700ms ease-out both;
```

- [ ] **Step 2: 호출부를 유틸리티 클래스로 교체**

`src/app/page.tsx`, `src/features/upload/progress.tsx`, `src/features/analysis/portfolio/amount-range-meter.tsx`에서 커스텀 클래스를 위 유틸리티 이름으로 바꾼다.

주의할 점:

- 지연(`animation-delay`)만 다른 변형(`evidence-source-2`, `evidence-signal-3`, `evidence-result-row-2` 등)은 tw-animate-css의 `delay-*` 유틸리티로 대체한다. 예: `delay-[140ms]`
- `::before`/`::after` 의사요소에 붙은 애니메이션(`.evidence-source::after`)은 클래스로 옮길 수 없다. **이런 항목은 CSS에 그대로 남기고**, `@theme` 토큰을 `animation` 속성에서 `var(--animate-evidence-scan)`으로 참조해 정의만 한 곳으로 모은다.
- `.evidence-weave`, `.evidence-dot-grid`, `.evidence-route`, `.evidence-stitch` 등 애니메이션이 아닌 순수 스타일 클래스는 **그대로 둔다.**
- 랜딩 히어로는 SVG 기반이다. 애니메이션 클래스를 `<svg>`나 그 자식 요소로 **옮기지 말고**, 지금처럼 감싸는 요소에 유지한다. SVG 요소를 직접 애니메이션하면 브라우저가 매 프레임 재래스터화해 비용이 커진다.

- [ ] **Step 3: reduced-motion 처리 확장**

Task 3에서 만든 전역 규칙에 새 클래스를 추가한다. 의사요소 애니메이션까지 확실히 멈추도록 포괄 규칙을 쓴다.

```css
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

이 포괄 규칙이 Task 3의 `.animate-enter` 전용 규칙을 대체하므로, 그 전용 규칙은 **제거한다.**

- [ ] **Step 4: 잔여 참조 확인**

```bash
cd frontend && grep -rn "analysis-pixel-loader\|amount-range-fill" src --exclude=globals.css
```

Expected: 출력 없음.

- [ ] **Step 5: 시각 회귀 직접 확인**

```bash
cd frontend && pnpm dev
```

브라우저에서 `/`(랜딩 히어로 루프 연출)와 `/upload`(픽셀 로더)를 열어 애니메이션이 이전과 같은 속도·리듬으로 재생되는지 확인한다. OS의 "동작 줄이기" 설정을 켠 상태에서도 한 번 확인한다.

- [ ] **Step 6: 검증**

```bash
cd frontend && pnpm test && pnpm lint && pnpm typecheck && pnpm format:check && pnpm build
```

Expected: 전부 통과.

- [ ] **Step 7: 커밋**

```bash
cd frontend && git add src/app/globals.css src/app/page.tsx src/features
git commit -m "refactor: register screen animations as theme tokens"
```

---

## Task 6: 업로드 폼 → 로딩 화면 전환 부드럽게

`form.tsx:109`에서 `isAnalyzing`이 true가 되는 순간 폼이 `AnalysisProgress`로 교체된다. `surface === "page"`일 때 이것은 `fixed inset-0 z-50 bg-white` 전체화면 오버레이라, 제출 버튼을 누르면 화면이 흰색으로 번쩍 바뀐다.

오버레이에 페이드 인을 주면 흰 배경이 서서히 폼을 덮는 형태가 되어 이음새가 사라진다. **폼의 이탈 애니메이션은 필요 없다** — 언마운트되는 폼을 붙잡아 둘 상태를 만들지 않아도 된다.

**Files:**
- Modify: `frontend/src/features/upload/progress.tsx:77-96`

**Interfaces:**
- Consumes: Task 3의 `animate-enter`, `animate-enter-overlay`
- Produces: 없음

- [ ] **Step 1: 오버레이와 콘텐츠에 진입 연출 적용**

`progress.tsx`의 `<section>` className 삼항에서 `page` 분기에만 `animate-enter-overlay`를 더한다. `modal` 분기는 다이얼로그 자체가 이미 진입 연출을 가지므로 **건드리지 않는다.**

```tsx
    <section
      role="status"
      className={`${
        surface === "modal"
          ? "flex w-full max-w-none flex-col items-center py-8 text-center"
          : "animate-enter-overlay fixed inset-0 z-50 flex items-center justify-center bg-white px-6 py-10 text-center"
      }`}
    >
```

내부 콘텐츠 블록에도 진입 연출을 준다. 오버레이(300ms)보다 늦게 시작해 배경이 먼저 덮이고 내용이 올라오게 한다.

```tsx
      <div className="animate-enter flex w-full max-w-[760px] flex-col items-center delay-150">
```

- [ ] **Step 2: 직접 확인**

```bash
cd frontend && pnpm dev
```

`/upload`에서 PDF를 골라 제출한다. 폼이 번쩍 사라지는 대신 흰 화면이 부드럽게 덮이고 내용이 뒤따라 올라오는지 본다.

- [ ] **Step 3: 검증**

```bash
cd frontend && pnpm test && pnpm lint && pnpm typecheck && pnpm format:check
```

Expected: 전부 통과. `progress.test.tsx`는 클래스가 아닌 표시 내용을 검증하므로 영향받지 않는다.

- [ ] **Step 4: 커밋**

```bash
cd frontend && git add src/features/upload/progress.tsx
git commit -m "feat: fade in the analysis progress overlay"
```

---

## Task 7: 진행바 완료 비트

`progress.tsx`의 trickle은 진행 중인 파일 몫의 90%까지만 채운다(의도된 설계 — 가짜 완료를 만들지 않기 위함). 문제는 마지막 파일이 끝나 `milestonePercent`가 100이 되는 tick에 `use-orchestration.ts`의 `saveSelectedNameAnalysis`가 곧바로 화면을 넘겨버려, 바가 100%까지 차오르는 프레임을 사용자가 볼 수 없다는 것이다.

완료를 잠깐 보여준 뒤 넘어가게 만든다. `use-orchestration.ts`는 이미 470줄이라 여기에 타이머를 얹지 않고, 대기 로직은 이름이 드러나는 hook으로 분리한다.

**Files:**
- Create: `frontend/src/features/upload/use-completion-beat.ts`
- Create: `frontend/src/features/upload/use-completion-beat.test.ts`
- Modify: `frontend/src/features/upload/use-orchestration.ts:84-96, 424-437`
- Modify: `frontend/src/features/upload/progress.tsx`
- Modify: `frontend/src/features/upload/form.tsx:109-121`
- Modify: `frontend/src/features/upload/progress.test.tsx`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `useCompletionBeat(): { isCompleting: boolean; runAfterBeat: (action: () => void) => void }` — `runAfterBeat`를 호출하면 `isCompleting`이 즉시 true가 되고, 400ms 뒤 `action`이 실행된다. 언마운트 시 타이머를 정리하고 `action`을 실행하지 않는다.
  - `AnalysisProgress`의 새 prop `isCompleting: boolean`

- [ ] **Step 1: 실패하는 테스트 작성**

`src/features/upload/use-completion-beat.test.ts`:

```ts
import { describe, expect, test, vi, beforeEach, afterEach } from "vitest";
import { act, renderHook } from "@testing-library/react";

import { useCompletionBeat } from "./use-completion-beat";

describe("useCompletionBeat", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  test("marks completing immediately and runs the action after the beat", () => {
    const action = vi.fn();
    const { result } = renderHook(() => useCompletionBeat());

    expect(result.current.isCompleting).toBe(false);

    act(() => result.current.runAfterBeat(action));
    expect(result.current.isCompleting).toBe(true);
    expect(action).not.toHaveBeenCalled();

    act(() => void vi.advanceTimersByTime(400));
    expect(action).toHaveBeenCalledOnce();
  });

  test("does not run the action after unmount", () => {
    const action = vi.fn();
    const { result, unmount } = renderHook(() => useCompletionBeat());

    act(() => result.current.runAfterBeat(action));
    unmount();
    act(() => void vi.advanceTimersByTime(400));

    expect(action).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: 실패 확인**

```bash
cd frontend && pnpm vitest run src/features/upload/use-completion-beat.test.ts
```

Expected: FAIL — `Failed to resolve import "./use-completion-beat"`

- [ ] **Step 3: hook 구현**

`src/features/upload/use-completion-beat.ts`:

```ts
"use client";

import { useEffect, useRef, useState } from "react";

// The progress bar deliberately trickles only to 90% so it never fakes a
// finish. This holds the finished state on screen briefly so the bar can
// actually reach 100% before the caller navigates away.
const COMPLETION_BEAT_MS = 400;

export function useCompletionBeat() {
  const [isCompleting, setIsCompleting] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const runAfterBeat = (action: () => void) => {
    setIsCompleting(true);
    timerRef.current = setTimeout(action, COMPLETION_BEAT_MS);
  };

  return { isCompleting, runAfterBeat };
}
```

- [ ] **Step 4: 통과 확인**

```bash
cd frontend && pnpm vitest run src/features/upload/use-completion-beat.test.ts
```

Expected: PASS (2 tests)

- [ ] **Step 5: 완료 표시에 대한 실패 테스트 작성**

`src/features/upload/progress.test.tsx`에 추가한다. 기존 파일의 import와 렌더 helper 형태를 먼저 읽고 맞춘다.

```tsx
  test("shows a finished state when completing", () => {
    render(
      <AnalysisProgress
        progress={{ completed: 2, total: 2 }}
        files={[
          { name: "a.pdf", status: "done" },
          { name: "b.pdf", status: "done" },
        ]}
        surface="page"
        isCompleting
      />,
    );

    expect(screen.getByRole("progressbar")).toHaveAttribute(
      "aria-valuenow",
      "100",
    );
    expect(screen.getByText("다 읽었어요. 결과를 보여드릴게요.")).toBeVisible();
  });
```

- [ ] **Step 6: 실패 확인**

```bash
cd frontend && pnpm vitest run src/features/upload/progress.test.tsx
```

Expected: FAIL — `isCompleting` prop이 타입에 없고 완료 문구가 렌더되지 않음.

- [ ] **Step 7: AnalysisProgress에 완료 단계 반영**

`progress.tsx`에 상수를 추가한다. 이 문구는 "읽기를 마쳤다"는 사실만 말하고, 분석 결과에 대해서는 아무것도 단정하지 않는다.

```tsx
const COMPLETE_MESSAGE = "다 읽었어요. 결과를 보여드릴게요.";
```

prop을 추가한다.

```tsx
export function AnalysisProgress({
  progress,
  files,
  surface,
  isCompleting = false,
}: {
  progress: { completed: number; total: number };
  files: Array<{ name: string; status: "done" | "reading" }>;
  surface: "page" | "modal";
  isCompleting?: boolean;
}) {
```

파생 값 계산부에서 완료 단계를 우선한다.

```tsx
  const statusMessage = isCompleting
    ? COMPLETE_MESSAGE
    : statusMessages[messageIndex % statusMessages.length];
  // Real milestones floor the trickle so completed files always show through.
  const percent = isCompleting
    ? 100
    : Math.round(Math.max(displayPercent, milestonePercent));
```

- [ ] **Step 8: 통과 확인**

```bash
cd frontend && pnpm vitest run src/features/upload/progress.test.tsx
```

Expected: PASS

- [ ] **Step 9: use-orchestration에서 조립**

`use-orchestration.ts` 상단에 import를 추가한다.

```ts
import { useCompletionBeat } from "./use-completion-beat";
```

hook 본문의 상태 선언부 근처에서 호출한다.

```ts
  const { isCompleting, runAfterBeat } = useCompletionBeat();
```

`saveSelectedNameAnalysis`를 고친다. 호출부만 읽어도 "완료를 보여주고 나서 넘어간다"가 드러나야 한다.

```ts
  const saveSelectedNameAnalysis = (
    analysis: InsuranceAnalysis,
    personName: string,
  ) => {
    const filteredAnalysis = {
      ...analysis,
      selectedName: personName,
      insuranceDocuments: analysis.insuranceDocuments.filter(
        (insuranceDocument) =>
          getInsuredPersonName(insuranceDocument) === personName,
      ),
    };
    runAfterBeat(() => {
      completeAnalysis(filteredAnalysis);
      navigateToAnalysis();
    });
  };
```

반환값에 `isCompleting`을 추가한다.

```ts
  return {
    selectedUploadFiles,
    isAnalyzing,
    isCompleting,
    analysisProgress,
    // ...나머지 그대로
  };
```

실패 경로(`failSelectedFiles`, `rejectDuplicateFiles`, 오류 `setError`)에는 **적용하지 않는다.** 오류는 지금처럼 즉시 드러나야 한다.

- [ ] **Step 10: form.tsx에서 prop 전달**

구조 분해에 `isCompleting`을 추가하고 `AnalysisProgress`에 넘긴다.

```tsx
  if (isAnalyzing) {
    return (
      <AnalysisProgress
        progress={analysisProgress}
        files={selectedUploadFiles.map((selectedFile) => ({
          name: selectedFile.file.name,
          status:
            selectedFile.status === "done" ? "done" : ("reading" as const),
        }))}
        surface={surface}
        isCompleting={isCompleting}
      />
    );
  }
```

- [ ] **Step 11: 기존 폼 테스트 회귀 확인**

`form.test.tsx`는 `navigateToAnalysis`가 호출되는지 검증한다. 이제 400ms 지연이 생겼으므로 실제 타이머 기준으로 통과하는지 본다.

```bash
cd frontend && pnpm vitest run src/features/upload/form.test.tsx
```

Expected: PASS.

**FAIL이 나면** 해당 단언을 `waitFor`로 감싼다. 예:

```tsx
    await waitFor(() => expect(navigateToAnalysis).toHaveBeenCalledOnce());
```

- [ ] **Step 12: 전체 검증**

```bash
cd frontend && pnpm test && pnpm lint && pnpm typecheck && pnpm format:check && pnpm build
```

Expected: 전부 통과.

- [ ] **Step 13: 커밋**

```bash
cd frontend && git add src/features/upload
git commit -m "feat: let the progress bar reach 100% before leaving"
```

---

## Task 8: 탭 전환 진입 애니메이션

`screen.tsx`에서 분석 탭 패널만 내부 요소(`animate-enter`로 바뀐 것들)의 연출 덕에 진입 느낌이 있고, "내 보험"과 "AI 보험 상담" 탭은 없다. 세 패널을 감싸는 공통 래퍼에 같은 연출을 주어 통일한다.

**Files:**
- Modify: `frontend/src/features/analysis/screen.tsx:176-236`

**Interfaces:**
- Consumes: Task 3의 `animate-enter`
- Produces: 없음

- [ ] **Step 1: 탭 패널 래퍼 추가**

`screen.tsx`의 세 갈래 삼항 전체를 하나의 래퍼로 감싼다. `key={activeTab}`이 있어야 탭이 바뀔 때마다 재마운트되어 애니메이션이 다시 재생된다.

```tsx
        {sessionExpired ? <PolicySessionExpiredNotice /> : null}

        {/* key remounts the panel on tab change so the enter animation replays */}
        <div key={activeTab} className="animate-enter flex min-h-0 flex-1 flex-col">
          {activeTab === "insurance" ? (
            <InsuranceListPanel
              /* ...기존 prop 그대로... */
            />
          ) : activeTab === "analysis" ? (
            /* ...기존 분석 탭 JSX 그대로... */
          ) : (
            /* ...기존 상담 탭 JSX 그대로... */
          )}
        </div>
```

`InsuranceChatbot`은 탭이 바뀌어도 계속 살아 있어야 하므로 **래퍼 바깥에 그대로 둔다.**

- [ ] **Step 2: 레이아웃이 깨지지 않았는지 확인**

새 `div`가 flex 자식으로 끼어들면서 높이 계산이 달라질 수 있다. AI 상담 탭은 `h-dvh overflow-hidden` 환경에서 동작하므로 특히 주의한다.

```bash
cd frontend && pnpm dev
```

`/analysis`에서 세 탭을 모두 오가며 확인한다.
- 각 탭 내용이 부드럽게 나타나는가
- AI 상담 탭에서 대화 영역이 잘리거나 스크롤이 이중으로 생기지 않는가
- 내 보험 탭의 아코디언 펼침이 정상인가

레이아웃이 틀어지면 래퍼의 flex 클래스를 조정한다. 애니메이션보다 레이아웃이 우선이다.

- [ ] **Step 3: 검증**

```bash
cd frontend && pnpm test && pnpm lint && pnpm typecheck && pnpm format:check && pnpm build
```

Expected: 전부 통과. `screen.test.tsx`의 탭 전환 테스트가 그대로 통과해야 한다.

- [ ] **Step 4: 커밋**

```bash
cd frontend && git add src/features/analysis/screen.tsx
git commit -m "feat: animate every analysis tab panel on enter"
```

---

## Task 9: 스켈레톤 → 결과 전환 부드럽게

보장 합계와 분석 결과가 스켈레톤에서 결과로 바뀔 때 하드 컷이 발생한다. **결과 쪽에** 진입 연출을 주면 스켈레톤은 그대로 사라지고 결과가 페이드 인하며 올라온다.

**Files:**
- Modify: `frontend/src/features/analysis/portfolio/total-table.tsx`
- Modify: `frontend/src/features/analysis/portfolio/panel/index.tsx`

**Interfaces:**
- Consumes: Task 3의 `animate-enter`
- Produces: 없음

- [ ] **Step 1: 현재 분기 구조 파악**

```bash
cd frontend && grep -n "status\|Loading\|Error" src/features/analysis/portfolio/total-table.tsx src/features/analysis/portfolio/panel/index.tsx
```

`success` 상태에서 렌더되는 최상위 요소를 찾는다.

- [ ] **Step 2: 결과 요소에 animate-enter 적용**

각 파일에서 `status === "success"`일 때 렌더되는 **최상위 요소 하나에만** `animate-enter`를 붙인다. 내부 요소마다 붙이면 화면이 산만해진다.

스켈레톤(`CoverageSummaryLoading`, `AnalysisLoading`)은 그대로 둔다. 이 둘은 초기 로딩에서 한 번만 나타나므로 진입 연출이 필요 없다.

- [ ] **Step 3: 직접 확인**

```bash
cd frontend && pnpm dev
```

`/upload`에서 PDF를 올려 `/analysis`에 도착한 뒤, 스켈레톤이 결과로 바뀌는 순간을 본다. 툭 바뀌지 않고 부드럽게 올라와야 한다.

- [ ] **Step 4: 검증**

```bash
cd frontend && pnpm test && pnpm lint && pnpm typecheck && pnpm format:check && pnpm build
```

Expected: 전부 통과.

- [ ] **Step 5: 커밋**

```bash
cd frontend && git add src/features/analysis/portfolio
git commit -m "feat: fade in analysis results replacing skeletons"
```

---

## Task 10: 사망진단 카드 체크박스 전환

사망진단 카드의 체크박스를 바꾸면 `isRefreshing`이 켜지며 `coverage-reference.tsx:20-29`가 `h-28 animate-pulse` 회색 박스로 툭 바뀌고, 끝나면 툭 돌아온다. Task 9와 달리 여기는 **양방향**(결과 → 스켈레톤 → 결과)이라 스켈레톤 진입도 부드러워야 한다.

**Files:**
- Modify: `frontend/src/features/analysis/portfolio/recommendation-cards/coverage-reference.tsx:19-29`

**Interfaces:**
- Consumes: Task 3의 `animate-enter`
- Produces: 없음

- [ ] **Step 1: 양쪽에 진입 연출 적용**

스켈레톤 분기:

```tsx
  if (isRefreshing) {
    return (
      <div
        role="status"
        aria-label="권장금액을 다시 확인하고 있어요"
        aria-busy="true"
        aria-live="polite"
        className="animate-enter h-28 animate-pulse rounded-2xl bg-zinc-100"
      />
    );
  }
```

`animate-enter`와 `animate-pulse`는 같은 요소에서 충돌한다(둘 다 `animation` 속성). 충돌하면 바깥 `div`에 `animate-enter`, 안쪽 `div`에 `animate-pulse`로 나눈다.

```tsx
  if (isRefreshing) {
    return (
      <div
        role="status"
        aria-label="권장금액을 다시 확인하고 있어요"
        aria-busy="true"
        aria-live="polite"
        className="animate-enter"
      >
        <div className="h-28 animate-pulse rounded-2xl bg-zinc-100" />
      </div>
    );
  }
```

결과 분기의 최상위 `<Card>`에도 `animate-enter`를 더한다.

- [ ] **Step 2: 높이 흔들림 확인**

스켈레톤 높이는 `h-28`(112px)로 고정인데 실제 카드 높이가 크게 다르면 전환할 때마다 아래 콘텐츠가 튄다.

```bash
cd frontend && pnpm dev
```

`/analysis` → 보험 분석 탭 → 사망 보장 카드에서 체크박스를 켜고 끄며 확인한다. 아래 내용이 눈에 띄게 튀면 스켈레톤 높이를 실제 카드 높이에 가깝게 맞춘다.

- [ ] **Step 3: 검증**

```bash
cd frontend && pnpm test && pnpm lint && pnpm typecheck && pnpm format:check && pnpm build
```

Expected: 전부 통과.

- [ ] **Step 4: 커밋**

```bash
cd frontend && git add src/features/analysis/portfolio/recommendation-cards/coverage-reference.tsx
git commit -m "feat: smooth the death benefit card refresh transition"
```

---

## Task 11: PDF 암호 검사 중 표시

`use-selected-files.ts:52-69`의 `flagPasswordProtectedFiles`는 파일 선택 직후 `isPdfPasswordProtected`를 fire-and-forget으로 호출하지만, 검사 중임을 알리는 표시가 없다. 파일이 크면 눈에 띄는 시간이 걸리고, 그 사이 제출하면 암호 필드가 뜨기 전에 넘어가는 경합이 생긴다.

**Files:**
- Modify: `frontend/src/features/upload/types.ts:15`
- Modify: `frontend/src/features/upload/use-selected-files.ts:39-69`
- Modify: `frontend/src/features/upload/file-list.tsx:144-175`
- Modify: `frontend/src/features/upload/form.tsx`
- Modify: `frontend/src/features/upload/file-list.test.tsx`
- Modify: `frontend/src/features/upload/form.test.tsx`

**Interfaces:**
- Consumes: 없음
- Produces: `FileReadStatus`에 `"checking"` 추가. `"checking"` 상태의 파일이 하나라도 있으면 제출 버튼이 비활성화된다.

- [ ] **Step 1: 배지에 대한 실패 테스트 작성**

`src/features/upload/file-list.test.tsx`에 추가한다. 기존 파일의 render helper 형태를 먼저 읽고 맞춘다.

```tsx
  test("shows a checking badge while the password pre-check runs", () => {
    renderList({
      files: [
        {
          id: "1",
          file: new File(["x"], "insurance.pdf", { type: "application/pdf" }),
          status: "checking",
        },
      ],
    });

    expect(screen.getByText("확인 중")).toBeVisible();
  });
```

- [ ] **Step 2: 실패 확인**

```bash
cd frontend && pnpm vitest run src/features/upload/file-list.test.tsx
```

Expected: FAIL — `"checking"`이 `FileReadStatus`에 없어 타입 오류, 또는 "확인 중" 텍스트 없음.

- [ ] **Step 3: 타입에 checking 추가**

`src/features/upload/types.ts`:

```ts
export type FileReadStatus =
  | "idle"
  | "checking"
  | "reading"
  | "done"
  | "failed";
```

- [ ] **Step 4: 배지 렌더**

`file-list.tsx`의 `SelectedFileStatusBadge`에서, `status === "done"` 분기 **앞에** 추가한다. 실패·암호 분기가 먼저 오는 순서는 유지한다.

```tsx
  if (status === "checking") {
    return (
      <span className="rounded-md border border-zinc-200 bg-white px-1.5 py-0.5 text-[11px] font-semibold text-zinc-500">
        확인 중
      </span>
    );
  }
```

- [ ] **Step 5: 통과 확인**

```bash
cd frontend && pnpm vitest run src/features/upload/file-list.test.tsx
```

Expected: PASS

- [ ] **Step 6: 검사 중 상태를 실제로 세팅**

`use-selected-files.ts`의 `selectFiles`에서 초기 상태를 `"checking"`으로 바꾼다.

```ts
    const selectedFiles = incomingFiles.map((file, index) => ({
      id: `${Date.now()}-${index}-${file.name}-${file.size}`,
      file,
      status: "checking" as const,
    }));
```

`flagPasswordProtectedFiles`가 검사 결과와 무관하게 상태를 반드시 해제하도록 고친다. `isPdfPasswordProtected`는 실패 시 `false`로 fail-open하는데, 이 동작은 유지한다.

```ts
  // Fire-and-forget: check each newly selected file for an encryption
  // password so the field shows up before submit instead of after a failed
  // upload round trip. Matches by id so a removed/superseded file is a no-op.
  // The checking status must clear on every path, or submit stays locked.
  const flagPasswordProtectedFiles = (files: SelectedUploadFile[]) => {
    for (const selectedFile of files) {
      void isPdfPasswordProtected(selectedFile.file).then((needsPassword) => {
        setSelectedUploadFiles((current) =>
          current.map((currentFile) => {
            if (currentFile.id !== selectedFile.id) return currentFile;
            if (currentFile.status !== "checking") return currentFile;
            if (needsPassword && !currentFile.errorCode) {
              return {
                ...currentFile,
                status: "idle" as const,
                errorCode: "PDF_PASSWORD_REQUIRED",
                errorMessage: "PDF 비밀번호를 입력해주세요.",
              };
            }
            return { ...currentFile, status: "idle" as const };
          }),
        );
      });
    }
  };
```

- [ ] **Step 7: 제출 잠금에 대한 실패 테스트 작성**

`src/features/upload/form.test.tsx`에 추가한다. 기존 파일이 `isPdfPasswordProtected`를 어떻게 다루는지(모킹 여부) 먼저 확인하고 맞춘다. 검사가 끝나기 전 상태를 만들기 위해 해결되지 않는 Promise로 모킹한다.

```tsx
  test("blocks submit while the password pre-check is still running", async () => {
    const user = userEvent.setup();
    vi.mocked(isPdfPasswordProtected).mockReturnValue(new Promise(() => {}));
    renderForm({});

    await user.upload(
      screen.getByLabelText(/PDF/i),
      new File(["x"], "insurance.pdf", { type: "application/pdf" }),
    );

    expect(screen.getByText("확인 중")).toBeVisible();
    expect(
      screen.getByRole("button", { name: "내 보험 분석하기" }),
    ).toBeDisabled();
  });
```

- [ ] **Step 8: 실패 확인**

```bash
cd frontend && pnpm vitest run src/features/upload/form.test.tsx
```

Expected: FAIL — 버튼이 비활성화되지 않음.

- [ ] **Step 9: 제출 잠금 구현**

`form.tsx`의 파생 값 계산부에 추가한다.

```tsx
  const isCheckingPasswords = selectedUploadFiles.some(
    (selectedFile) => selectedFile.status === "checking",
  );
```

제출 버튼의 `disabled`에 이 조건을 더한다. 기존 조건은 그대로 두고 `||`로 잇는다.

`handleSubmit`에도 방어를 넣어, 버튼 외의 경로(Enter 키 등)로 제출되는 것을 막는다. `use-orchestration.ts`의 early return에 조건을 추가한다.

```ts
    const isCheckingPasswords = selectedUploadFiles.some(
      (selectedFile) => selectedFile.status === "checking",
    );
    if (
      selectedUploadFiles.length === 0 ||
      isAnalyzing ||
      pendingAnalysis ||
      isCheckingPasswords
    )
      return;
```

- [ ] **Step 10: 통과 확인**

```bash
cd frontend && pnpm vitest run src/features/upload/form.test.tsx
```

Expected: PASS

- [ ] **Step 11: fail-open 경로 테스트 추가**

검사가 실패해도 화면이 잠기면 안 된다.

```tsx
  test("unlocks submit when the password pre-check fails", async () => {
    const user = userEvent.setup();
    vi.mocked(isPdfPasswordProtected).mockResolvedValue(false);
    renderForm({});

    await user.upload(
      screen.getByLabelText(/PDF/i),
      new File(["x"], "insurance.pdf", { type: "application/pdf" }),
    );

    await waitFor(() =>
      expect(screen.queryByText("확인 중")).not.toBeInTheDocument(),
    );
    expect(
      screen.getByRole("button", { name: "내 보험 분석하기" }),
    ).toBeEnabled();
  });
```

```bash
cd frontend && pnpm vitest run src/features/upload/form.test.tsx
```

Expected: PASS

- [ ] **Step 12: markSelectedFilesReading 확인**

`markSelectedFilesReading`은 모든 파일을 `"reading"`으로 덮어쓰므로 `"checking"`이 남아 제출 후 잠기는 일은 없다. 코드를 읽어 확인만 하고, 문제가 있으면 고친다.

- [ ] **Step 13: 전체 검증**

```bash
cd frontend && pnpm test && pnpm lint && pnpm typecheck && pnpm format:check && pnpm build
```

Expected: 전부 통과.

- [ ] **Step 14: 커밋**

```bash
cd frontend && git add src/features/upload
git commit -m "feat: show a checking state during the pdf password pre-check"
```

---

## Task 12: 뒷정리와 최종 검증

이 작업은 파일을 넓게 훑으며 조금씩 고치는 성격이라 흔적이 남기 쉽다. "체계를 하나로 통일"이라는 목적이 실제로 달성됐는지 확인한다.

**Files:**
- Modify: 점검 결과 발견된 파일

**Interfaces:**
- Consumes: Task 1~11 전부
- Produces: 없음

- [ ] **Step 1: 이전이 끝난 클래스가 남아 있지 않은지 확인**

```bash
cd frontend && grep -rn "analysis-overview-reveal\|analysis-overview-delay\|analysis-status-message\|analysis-status-fade\|analysis-coverage-orbit\|analysis-coverage-node\|premium-position\|overview-breathe\|analysis-pixel-loader" src
```

Expected: 출력 없음.

- [ ] **Step 2: globals.css에 죽은 keyframes가 없는지 확인**

`globals.css`의 각 `@keyframes` 이름을 `@theme` 토큰과 CSS 클래스에서 검색해, 아무도 참조하지 않는 것이 있으면 제거한다.

```bash
cd frontend && grep -o "@keyframes [a-z-]*" src/app/globals.css | sed 's/@keyframes //' | while read -r name; do
  count=$(grep -c "$name" src/app/globals.css)
  [ "$count" -le 1 ] && echo "DEAD: $name"
done
echo "(DEAD 출력이 없으면 정상)"
```

- [ ] **Step 3: 미사용 import·export 확인**

```bash
cd frontend && pnpm lint
```

Expected: 경고 없음.

- [ ] **Step 4: globals.css 구획 정리**

파일이 읽기 쉽게 두 구획으로 나뉘고 각 구획에 짧은 영어 주석이 있는지 확인한다.

- 모션 토큰 (`@theme` 안)
- 화면 전용 keyframes와 스타일 클래스

- [ ] **Step 5: reduced-motion 실제 확인**

```bash
cd frontend && pnpm dev
```

OS 설정에서 "동작 줄이기"를 켜고 `/`, `/upload`, `/analysis`를 모두 확인한다. 애니메이션이 재생되지 않으면서도 **모든 콘텐츠가 정상적으로 보여야** 한다. `animation: none`으로 `opacity: 0`에 갇혀 안 보이는 요소가 없는지 특히 주의한다.

- [ ] **Step 6: 전체 흐름 직접 확인**

`/` → `/upload` → PDF 업로드 → `/analysis` → 세 탭 전환 → 사망 보장 카드 체크박스까지 한 번에 훑으며, 8개 지점이 모두 부드러운지 확인한다.

- [ ] **Step 7: 최종 검증**

```bash
cd frontend && pnpm api:check && pnpm test && pnpm lint && pnpm typecheck && pnpm format:check && pnpm build
```

Expected: 전부 통과.

- [ ] **Step 8: 커밋**

변경 사항이 있을 때만 커밋한다.

```bash
cd frontend && git add -A && git commit -m "chore: clean up leftover animation css"
```
