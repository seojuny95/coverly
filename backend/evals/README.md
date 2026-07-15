# backend/evals

`evals`는 품질 회귀를 측정하는 전용 영역이다. 런타임 코드인 `app`와 분리하고, correctness는 `backend/tests`가 담당한다.

## 범위

- `backend/evals/rag/official`: 공식 약관·제도 RAG retrieval/generation 평가
- `backend/evals/rag/policy`: 업로드 세션 RAG retrieval/generation 평가

## 실행

모든 명령은 `backend/`에서 실행한다.

```bash
uv run python -m evals.rag.official.retrieval
uv run python -m evals.rag.official.generation --show-passing
uv run python -m evals.rag.policy.retrieval
uv run python -m evals.rag.policy.generation --set practice --show-passing
uv run python -m evals.rag.policy.generation --set test
```

## 규칙

- `app`는 `evals`를 import하지 않는다.
- `evals`는 API correctness 테스트를 대체하지 않는다.
- practice와 test 데이터셋은 분리해서 관리한다.
