# backend/evals

`evals`는 품질 회귀를 측정하는 전용 영역이다. 런타임 코드인 `app`와 분리하고, correctness는 `backend/tests`가 담당한다.

## 범위

- `backend/evals/qa`: 실제 `POST /qa/stream`을 태우는 라이브 상담 평가. `rules.py`는 API 키 없이 도는 결정적 검사(근거 없는 금액, 도구 인자에 남은 지시어 등), `judge.py`는 `--judge`로 켜는 LLM 심사(말투·조언·범위 밖 거절 등)
- `backend/evals/rag/official`: 공식 약관·제도 RAG retrieval/generation 평가
- `backend/evals/rag/policy`: 업로드 세션 RAG extraction/retrieval/generation 평가

## 실행

모든 명령은 `backend/`에서 실행한다.

```bash
uv run python -m evals.qa.live
uv run python -m evals.qa.live --judge
uv run python -m evals.qa.live --case fact_coverage_exact --json report.json
uv run python -m evals.rag.official.retrieval
uv run python -m evals.rag.official.generation --show-passing
uv run python -m evals.rag.official.e2e
uv run python -m evals.rag.policy.extraction --show-passing
uv run python -m evals.rag.policy.retrieval
uv run python -m evals.rag.policy.generation --set practice --show-passing
uv run python -m evals.rag.policy.generation --set test
uv run python -m evals.rag.policy.e2e
```

Official/Policy E2E는 같은 실행 모드를 사용한다.

```bash
# 빠르고 결정적인 로컬 회귀 기준선
uv run python -m evals.rag.official.e2e \
  --retrieval-mode offline --generation-mode deterministic
uv run python -m evals.rag.policy.e2e \
  --retrieval-mode offline --generation-mode deterministic

# 운영 retrieval 효과만 분리해서 측정
uv run python -m evals.rag.official.e2e \
  --retrieval-mode production --generation-mode deterministic
uv run python -m evals.rag.policy.e2e \
  --retrieval-mode production --generation-mode deterministic

# 실제 retrieval과 LLM generation을 모두 포함한 Online E2E
uv run python -m evals.rag.official.e2e \
  --retrieval-mode production --generation-mode live
uv run python -m evals.rag.policy.e2e \
  --retrieval-mode production --generation-mode live
```

`production` retrieval과 `live` generation에는 `DATABASE_URL`과 OpenAI 설정이
필요하다. Policy production 평가는 실행별 고유 `eval-*` 세션에 평가용 vector를
임시 적재하고, 성공·실패와 관계없이 종료 시 삭제한다.

E2E 보고서는 실행 모드, retrieval/generation 모델, 실행 시각, corpus/index
fingerprint와 retrieval/generation/전체 latency의 평균·p95를 함께 출력한다.
점수를 비교할 때는 같은 corpus/index와 같은 실행 모드끼리 비교한다.

## 규칙

- `app`는 `evals`를 import하지 않는다.
- `evals`는 API correctness 테스트를 대체하지 않는다.
- practice와 test 데이터셋은 분리해서 관리한다.
- policy extraction 데이터셋은 개인정보 원문을 fixture에 저장하지 않는다. 필요한 경우
  `{mobile_phone}` 같은 심볼만 저장하고 실행 중 메모리에서 합성값을 만들어 마스킹을
  검증한다.
- 상담 라이브 평가는 planner와 agent를 실제로 호출한다. 포트폴리오 세션만 fixture 증권으로 대체하고
  나머지 경로는 운영과 같다. OpenAI 호출이 발생하므로 반복 실행 횟수를 의식해서 쓴다.
- 상담 라이브 결과는 단일 실행으로 판단하지 않는다. `--runs N`으로 반복해 케이스별 통과율을 보고,
  회귀와 실행별 변동을 구분한다.
- retrieval 평가는 답변 가능한 positive 질문의 근거 회수율과 랭킹을 주 품질 지표로 본다.
- out-of-scope/negative 질문의 답변 거절은 retrieval이 아니라 router/generation/e2e 평가에서 품질 gate로 다룬다.
- RAG e2e 평가는 상담 router/planner를 거치지 않고 `retrieval → generation` 연결만 본다.
