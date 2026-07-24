# Coverly AI frontend

Next.js App Router 기반 프론트엔드 앱이다.

## 실행

```bash
pnpm install
pnpm dev
```

기본 백엔드 주소는 `http://localhost:8000`이다. 다른 주소를 사용하면
`NEXT_PUBLIC_API_BASE_URL`을 설정한다. 포트폴리오당 PDF는 최대 5개까지 선택할 수
있고 파일당 최대 크기는 10MB다. 파일 수·크기 한도는 백엔드 OpenAPI 계약에서
생성된 상수를 사용하며, 100쪽 제한은 서버가 업로드 후 검증한다.

React Compiler는 `next.config.ts`의 `reactCompiler: true`로 활성화되어 있다.

## 상태와 오류 처리

- 증권·분석 결과·세션 토큰은 브라우저 메모리에만 두며 새로고침하면 사라진다.
- 사용자 메시지는 내부 예외와 분리한다. 개발자 진단에는 오류명·코드·요청 ID·상태
  코드만 남기고 증권 내용이나 질문 원문을 기록하지 않는다.
- 업로드 전에는 유휴 상태의 백엔드가 깨어날 시간을 주기 위해 `/ready`를 확인한다.
  `/health`는 프로세스 생존만, `/ready`는 DB·세션 저장소 준비 상태까지 확인한다.
- 자동 재시도는 안전한 요청에만 제한적으로 적용한다. PDF 업로드는 서버가 파싱
  대기 상태를 명시한 경우에만, LLM 총평은 명시적인 일시 오류에만 재시도한다.
  완료 여부가 모호한 요청은 자동으로 반복하지 않는다.

## 검증

```bash
pnpm api:check
pnpm test
pnpm lint
pnpm typecheck
pnpm format:check
pnpm build
```
