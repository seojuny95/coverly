# 프론트엔드 로딩·전환 애니메이션 정리 — 설계

## 배경

현재 프론트엔드에는 애니메이션 체계가 두 갈래로 존재하고, 그중 한쪽은 동작하지 않는다.

- **직접 쓴 CSS keyframes (동작함)** — `globals.css`에 12개. 랜딩 히어로, 업로드 픽셀 로더, 금액 범위 미터, 상태 문구 페이드.
- **shadcn/ui가 전제하는 `tw-animate-css` 유틸 (동작 안 함)** — `data-open:animate-in`, `fade-in-0`, `zoom-in-95`, `slide-in-from-bottom-2` 등이 컴포넌트 클래스 문자열에 적혀 있으나, 해당 패키지가 `package.json`에도 `globals.css`에도 없다. Tailwind v4 코어에 없는 클래스라 조용히 무시된다.

그 결과 모달·툴팁·상담 배너가 애니메이션 없이 뚝 나타나고, 로딩 상태들이 서로 다른 인상을 준다.

## 목표

애니메이션 체계를 `tw-animate-css` 하나로 통일하고, 사용자가 어색하다고 지적한 8개 지점의 이음새를 다듬는다. 연출을 화려하게 만드는 것이 목적이 아니라, **상태가 바뀌는 순간이 하드 컷으로 튀지 않게** 하는 것이 목적이다.

## 비목표

- motion(Framer Motion) 등 JS 모션 라이브러리 도입 — 요청 항목 대부분이 진입 전용이라 값을 못 한다.
- 페이지 라우트 전환(`/upload` → `/analysis`) 애니메이션 — 사이에 1~2분 로딩 화면이 있어 사용자가 전환을 체감하지 않는다.
- 분석 페이지 도착 후 스켈레톤이 다시 뜨는 것 자체 — 자연스러운 동작으로 판단해 유지한다.
- 새로운 연출·모션 언어 발명. 기존 인상을 유지한다.

## 공통 모션 규칙

모든 진입 애니메이션은 하나의 규칙을 따른다.

- **진입**: 페이드 + 아래에서 위로 살짝, 4px, 200ms, `ease-out`
- **접근성**: `prefers-reduced-motion` 사용자에게는 재생하지 않고 즉시 표시한다. 무한 루프 연출도 멈춘다.

과하지 않게 — 거리는 4px 내외, 시간은 200ms 내외로 제한한다.

### 규칙을 이름 하나로 만든다

`motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-1 motion-safe:duration-200`을 8개 지점에 복붙하면, 규칙이 문자열 중복으로 흩어져 나중에 한 곳만 바뀌어도 알 수 없다.

대신 `globals.css`의 `@theme`에 **의미 있는 이름의 애니메이션 토큰**을 정의하고, 컴포넌트는 그 이름 하나만 쓴다.

```
@theme {
  --animate-enter: <진입 규칙>;
  --animate-enter-overlay: <오버레이용, 좀 더 느리게>;
}
```

컴포넌트에서는 `className="animate-enter"` 한 마디로 끝난다. `prefers-reduced-motion` 처리도 토큰 정의 안에 넣어, 사용처에서 매번 신경 쓰지 않게 한다. 규칙을 바꿔야 하면 `@theme` 한 곳만 고친다.

이 토큰 정의는 `globals.css` 안에서 **모션 토큰 / 화면 전용 keyframes** 두 구획으로 나누고, 각 구획이 무엇을 담는지 짧은 주석으로 표시한다.

## 작업 항목

### 1. tw-animate-css 설치

`pnpm add -D tw-animate-css` 후 `globals.css` 상단에 `@import "tw-animate-css";`를 추가한다.

이것만으로 이미 코드에 적혀 있는 클래스가 살아나며 다음이 복구된다.

| 위치 | 복구되는 동작 |
| --- | --- |
| `shared/components/ui/dialog.tsx` | 업로드 모달 열림/닫힘 |
| `shared/components/ui/alert-dialog.tsx` | 이탈 경고 다이얼로그 |
| `shared/components/ui/tooltip.tsx` | 툴팁 |
| `features/analysis/portfolio/chatbot.tsx` | 상담 안내 배너 |

기존 클래스 문자열은 수정하지 않는다.

### 2. 기존 keyframes 12개 이전

`globals.css`의 커스텀 keyframes를 정리해 체계를 하나로 만든다. 두 갈래로 나눠 처리한다.

**(a) 유틸리티로 대체 가능한 것 — 클래스로 교체하고 keyframes 삭제**

- `analysis-status-fade` → `motion-safe:animate-in motion-safe:fade-in`
- `analysis-overview-reveal` → `motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-2`
- `analysis-coverage-node` → 같은 조합 + `motion-safe:delay-*`

**(b) 유틸리티로 표현 불가능한 것 — `@theme`에 등록**

랜딩 히어로의 무한 루프 연출(`evidence-scan`, `evidence-signal`, `evidence-glow`, `evidence-result-row`, `evidence-complete`, `analysis-overview-breathe`), 업로드 픽셀 로더(`analysis-pixel-pulse`), 금액 미터(`amount-range-fill`, `premium-position-marker`)는 스텝 타이밍과 다중 키프레임에 의존해 유틸리티 조합으로 옮길 수 없다.

이들은 keyframes 정의를 유지하되 `@theme`의 `--animate-*` 토큰으로 등록해 **호출부는 다른 항목과 동일하게 `animate-<name>` 클래스로 통일**한다. 정의는 `@theme` 한 곳에 모이고, 컴포넌트는 전부 유틸리티 클래스만 쓴다.

이전 후 `.analysis-overview-reveal` 같은 컴포넌트 전용 CSS 클래스는 `globals.css`에서 제거한다.

### 3. 업로드 폼 → 로딩 화면 전환

`features/upload/form.tsx`에서 `isAnalyzing`이 true가 되는 순간 폼 전체가 `AnalysisProgress`(`fixed inset-0 z-50 bg-white` 전체화면)로 교체되며 하드 컷이 발생한다.

`AnalysisProgress`의 `surface === "page"` 오버레이에 진입 연출을 준다.

- 오버레이: `motion-safe:animate-in motion-safe:fade-in motion-safe:duration-300`
- 내부 콘텐츠 블록: 같은 페이드 + `slide-in-from-bottom-2`를 약간의 지연과 함께

폼의 이탈 애니메이션은 넣지 않는다. 폼은 즉시 언마운트되고 그 위로 오버레이가 페이드 인하므로, 흰 배경이 서서히 덮는 형태가 되어 이음새가 사라진다. React 언마운트를 붙잡아 두는 추가 상태 없이 해결된다.

`surface === "modal"`에는 적용하지 않는다(모달 자체가 이미 진입 연출을 가짐).

### 4. 진행바 완료 비트

`features/upload/progress.tsx`의 trickle은 진행 중인 파일 몫의 90%까지만 채우도록 설계돼 있다. 마지막 파일이 끝나 `milestonePercent`가 100이 되는 tick에 `use-orchestration.ts`의 `router.push("/analysis")`가 같이 실행되어, 바가 100%까지 차오르는 프레임을 사용자가 볼 수 없다.

분석 완료 후 화면 이동 전에 약 400ms의 완료 구간을 둔다. 이 구간 동안 진행률은 100%로 채워지고, 상태 문구는 완료를 알리는 한 줄로 바뀐다.

**구조**: `use-orchestration.ts`는 이미 470줄이라 여기에 타이머를 더 얹지 않는다. 대신 완료 구간을 `AnalysisProgress`가 표현할 수 있게 **표시 단계(진행 중 / 완료)를 prop으로 받도록** 하고, 그 단계를 넘기는 대기 로직은 이름이 드러나는 별도 hook으로 뺀다. `use-orchestration.ts`의 호출부에서는 "완료를 보여주고 나서 이동한다"는 흐름이 한눈에 보여야 한다.

- 지연 타이머는 언마운트 시 반드시 정리한다.
- 실패 경로에는 적용하지 않는다. 오류는 지금처럼 즉시 드러나야 한다.
- 완료 문구는 `UX_COPY.md` 기준을 따르고, 서버가 확인하지 않은 사실을 단정하지 않는다.
- `AnalysisProgress`는 이미 타이머 3개(trickle·문구 순환·경과 시간)를 들고 있다. 단계 prop을 받으면서 파일이 더 복잡해지면, 타이머 묶음을 hook으로 분리해 컴포넌트는 표시에만 집중하게 한다.

### 5. 탭 전환

`features/analysis/screen.tsx`에서 분석 탭 패널만 내부 요소의 커스텀 애니메이션 덕에 진입 연출이 있고, 내 보험 탭과 AI 상담 탭은 없다.

세 탭 패널을 감싸는 공통 래퍼에 동일한 진입 연출을 적용한다. 탭이 바뀔 때마다 재생되어야 하므로 래퍼에 `key={activeTab}`을 준다.

이탈 애니메이션은 넣지 않는다. 이전 패널을 붙잡아 두려면 별도 상태 관리가 필요한데, 진입 연출만으로 충분하다.

### 6. 보장 합계 로딩 → 결과 표시

`portfolio/total-table.tsx`와 `portfolio/panel/analysis-loading.tsx`의 스켈레톤이 결과로 바뀔 때 하드 컷이 발생한다.

스켈레톤이 아니라 **결과 쪽에** 진입 연출을 준다. 스켈레톤은 그대로 사라지고 결과가 페이드 인하며 올라온다.

### 7. 사망진단 카드 체크박스 변경

체크박스를 바꾸면 `isRefreshing`이 켜지며 `recommendation-cards/coverage-reference.tsx`가 `h-28 animate-pulse` 회색 박스로 툭 바뀌고, 끝나면 툭 돌아온다.

스켈레톤과 결과 양쪽에 진입 연출을 준다. 항목 6과 달리 여기는 **양방향 전환**(결과 → 스켈레톤 → 결과)이라 스켈레톤 진입도 부드러워야 한다.

- 스켈레톤: `motion-safe:animate-in motion-safe:fade-in`
- 결과 복귀: 공통 진입 규칙

높이가 요동치지 않도록 스켈레톤 높이(`h-28`)와 실제 콘텐츠 높이 차이를 확인하고, 크게 다르면 스켈레톤 높이를 맞춘다.

### 8. PDF 암호 체크 표시

`features/upload/use-selected-files.ts`가 파일 선택 직후 `isPdfPasswordProtected`를 비동기로 호출하지만, 검사 중임을 알리는 표시가 없다. 파일이 크면 눈에 띄는 시간이 걸린다.

선택한 파일의 상태에 검사 중을 나타내는 값을 추가하고, `features/upload/file-list.tsx`에서 해당 파일 행에 "확인 중" 표시를 낸다.

- 표시는 기존 파일 상태 배지와 같은 자리·같은 스타일을 쓴다.
- 검사 중인 파일이 있으면 제출 버튼을 비활성화해, 암호 필드가 뜨기 전에 제출되는 경합을 막는다.
- `isPdfPasswordProtected`는 실패 시 `false`를 반환하며 fail-open하는데, 이 동작은 유지한다. 검사 중 상태는 성공·실패 어느 쪽으로 끝나도 반드시 해제한다.

## 코드 구조와 가독성

이 작업은 파일을 넓게 훑으며 조금씩 고치는 성격이라, 손대는 곳마다 흔적이 남기 쉽다. 아래를 완료 조건으로 본다.

**공통 경계**

- 모션 규칙은 `@theme` 토큰 한 곳에 정의하고, 컴포넌트는 이름만 쓴다. 같은 클래스 조합이 두 곳 이상에 나타나면 토큰으로 올린다.
- 스켈레톤은 이미 `shared/components/ui/skeleton.tsx`가 있다. 진입 연출이 여러 스켈레톤에 반복되면 각 사용처가 아니라 `Skeleton`에 넣는다.
- 탭 패널 래퍼처럼 세 곳이 같은 구조를 갖게 되는 것은 이름 있는 하위 컴포넌트로 만든다. 다만 이름만 공통인 억지 추상화는 만들지 않는다.

**로직과 표시의 분리**

- 타이머·대기·상태 전이는 hook으로, 컴포넌트는 받은 값을 그리는 데만 집중한다.
- 새로 만드는 hook과 컴포넌트는 이름만 보고 역할이 드러나야 한다. 호출부를 읽었을 때 "무엇을 기다렸다가 무엇을 보여주는지"가 보여야 한다.

**파일과 폴더**

- 파일이 커지면 기능 폴더 안에서 나눈다. `features/upload/`, `features/analysis/portfolio/` 등 기존 구조를 따르고 새 최상위 폴더를 만들지 않는다.
- 파일명은 kebab-case, 기능명을 prefix로 반복하지 않는다.
- 한 컴포넌트 파일이 여러 하위 컴포넌트로 커지면 같은 이름의 폴더 + `index.tsx`로 나눠 import 경로를 유지한다.

**주석**

- 코드를 풀어쓴 설명은 쓰지 않는다. 왜 이 지연을 두는지, 왜 이 경로에는 적용하지 않는지 같은 **이유와 제약만** 영어로 짧게 남긴다.
- 작업 중 발견한 낡은 주석은 정리한다.

**뒷정리**

- 이전이 끝난 keyframes와 컴포넌트 전용 CSS 클래스는 반드시 제거한다. 남겨두면 "두 갈래 체계 통일"이라는 이 작업의 목적 자체가 무너진다.
- 미사용 import·export, 참조되지 않는 파일이 남지 않았는지 마지막에 검색해 확인한다.

## 경계와 원칙

- **서버 사실을 만들지 않는다** — 완료 문구를 포함해 어떤 애니메이션도 서버가 확인하지 않은 내용을 단정하지 않는다.
- **클라이언트 경계를 늘리지 않는다** — 전부 CSS 유틸리티라 새 `"use client"`가 필요 없다.
- **렌더링 비용** — 모두 `transform`/`opacity` 기반이라 레이아웃을 재계산하지 않는다.

## 테스트

애니메이션 자체(클래스 문자열)는 검증 대상이 아니다. 구현이 아니라 **사용자가 보는 상태**를 검증한다.

| 항목 | 검증 내용 |
| --- | --- |
| 4 | 분석 완료 후 진행률 100%와 완료 문구가 보이고, 그 다음 `/analysis`로 이동한다 |
| 8 | 파일 선택 직후 "확인 중"이 보이고, 검사가 끝나면 사라진다 |
| 8 | 검사 중에는 제출 버튼이 비활성화된다 |
| 8 | 검사가 실패해도 "확인 중"이 사라지고 제출이 가능해진다 |
| 5 | 탭을 바꾸면 해당 패널의 내용이 보인다 (기존 테스트 유지 확인) |

항목 1·2·3·6·7은 시각 변경이라 자동 테스트를 추가하지 않고, 기존 테스트가 깨지지 않는 것으로 회귀를 막는다.

## 검증

`pnpm api:check && pnpm test && pnpm lint && pnpm typecheck && pnpm format:check && pnpm build`

추가로 `globals.css`에서 제거한 클래스가 어디에도 남아 있지 않은지 검색해 확인한다.
