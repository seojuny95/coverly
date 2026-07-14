# Official RAG 평가

이 문서는 공식문서 RAG의 Retrieval과 Generation 품질을 서로 분리해 평가하는 기준을 정리한다.
Retrieval은 필요한 근거 chunk를 찾는 능력을, Generation은 고정된 근거에서 안전하고 충실한 답변을 만드는 능력을 본다.

Retrieval 평가셋은 **36개 시나리오 × 질문 표현 2개 = 72개 케이스**로 구성한다.
Generation 평가셋은 **30개 시나리오 × 질문 표현 2개 = 60개 케이스**로 구성한다.
같은 사실이나 질문 의도를 서로 다른 표현으로 물어 단순 키워드 일치에만 유리한 평가가 되지 않도록 한다.

## Retrieval 평가

Retrieval 평가는 [retrieval_dataset.json](retrieval_dataset.json)의 질문을 검색기에 넣고 상위 5개 결과를 평가한다.
문서 source나 핵심 문자열 대신, 사람이 확인한 정확한 `relevant_chunk_ids`를 정답 라벨로 사용한다.

### 데이터셋

각 시나리오는 다음 필드를 가진다.

- `id`: 시나리오 식별자.
- `questions`: 같은 의도를 서로 다르게 표현한 질문 배열. 현재 각 시나리오당 2개다.
- `profile`: `term_explain`, `claim_check`, `consumer_protection`, `out_of_scope` 중 하나다.
- `difficulty`: `easy`, `medium`, `hard` 중 하나다.
- `relevant_chunk_ids`: 질문에 답할 수 있는 관련 chunk ID. 동일한 내용을 담은 표준약관 변형 chunk도 허용 가능한 정답으로 함께 라벨링한다.
- `expected_no_hits`: 공식문서 검색 범위 밖 질문에서 결과가 없어야 하는지 나타낸다.

현재 72개 케이스 중 54개는 관련 근거가 있는 positive 케이스이고, 18개는 날씨·기기 지원·사용자 개인 계약값·뉴스·주가·병원 예약·앱 계정·개인 보장금액·실시간 정보처럼 공식문서로 답할 수 없는 negative 케이스다.

### 지표

모든 `@K` 지표는 현재 `K=5`로 계산한다.

| 지표 | 계산 기준 | 높으면 의미하는 것 |
|---|---|---|
| `pass_rate` | positive는 관련 chunk가 하나 이상 검색되고, negative는 검색 결과가 없으면 통과 | Retrieval 단독 기준의 전체 평가 계약을 잘 만족함 |
| `Recall@5` | positive 케이스 중 관련 chunk를 하나 이상 찾은 비율 | 필요한 근거를 덜 놓침 |
| `Precision@5` | 상위 5개 결과 중 관련 chunk의 비율을 positive 케이스 전체에서 평균 | 불필요한 chunk가 적음 |
| `MRR` | positive 케이스에서 첫 관련 chunk 순위 역수의 평균 | 관련 근거가 앞쪽에 배치됨 |
| `nDCG@5` | 관련 chunk의 순위별 이득을 이상적인 순서와 비교 | 여러 관련 근거의 전반적인 랭킹이 좋음 |
| `negative_no_hit_rate` | negative 케이스에서 검색 결과가 하나도 없었던 비율 | 검색기가 범위 밖 질문에도 후보를 반환하는지 확인함 |
| `average_latency_seconds` | 전체 검색 시간을 케이스 수로 나눈 값 | 검색 응답이 빠름 |

`Recall@5`, `Precision@5`, `MRR`, `nDCG@5`는 negative 케이스를 제외한 positive 케이스를 분모로 사용한다.
`pass_rate`에는 positive와 negative가 모두 포함된다.

### 실행 경로

오프라인 평가는 공식문서 chunk에 `HashingEmbedder`를 적용한 인메모리 경로를 사용한다.
빠르고 결정적이지만 운영 임베딩 품질을 대표하지 않으므로 ranking 회귀를 빠르게 확인하는 용도다.

```bash
cd backend
PYTHONPATH=. uv run python - <<'PY'
from app.services.rag.official.evaluation.retrieval import evaluate_retrieval

report = evaluate_retrieval()
print(
    report.pass_rate,
    report.recall,
    report.precision_at_k,
    report.mrr,
    report.ndcg_at_k,
    report.negative_no_hit_rate,
    report.average_latency_seconds,
)
PY
```

운영 평가는 OpenAI embedding과 실제 pgvector index를 사용한다.
`OPENAI_API_KEY`, `DATABASE_URL`과 최신 공식문서 index가 필요하며 유닛 테스트에서는 실행하지 않는다.

```bash
cd backend
PYTHONPATH=. uv run python - <<'PY'
from app.services.rag.official.evaluation.retrieval import evaluate_retrieval

report = evaluate_retrieval(production=True)
print(
    report.pass_rate,
    report.recall,
    report.precision_at_k,
    report.mrr,
    report.ndcg_at_k,
    report.negative_no_hit_rate,
    report.average_latency_seconds,
)
PY
```

### 결과 해석

- `Recall@5`가 낮으면 query 표현, embedding, 후보 검색 또는 chunk 라벨을 먼저 확인한다.
- `Recall@5`는 높고 `MRR`이나 `nDCG@5`가 낮으면 정답은 찾지만 순위가 뒤쪽이라는 뜻이다.
- `Precision@5`가 낮으면 Generation에 불필요한 context가 많이 전달될 수 있다.
- `negative_no_hit_rate`가 낮으면 검색기가 범위 밖 질문에도 후보를 반환한다는 뜻이다. 현재 Official RAG retrieval은 라우팅을 맡지 않으므로, 범위 밖 질문 거절은 상위 QA 라우터에서 별도로 평가해야 한다.
- 오프라인과 운영 결과 차이가 크면 HashingEmbedder 결과를 운영 품질로 해석하지 않는다.

## Generation 평가

Generation 평가는 [generation_dataset.json](generation_dataset.json)에 지정된 고정 근거 chunk를 [answer.py](../answer.py)의 `answer_official_question()`에 직접 전달한다.
Retrieval을 거치지 않기 때문에 실패하면 prompt, output contract, citation 처리 또는 답변 후처리를 먼저 의심한다.

### 데이터셋

각 시나리오는 다음 필드를 가진다.

- `id`: 시나리오 식별자.
- `questions`: 같은 의도를 서로 다르게 표현한 질문 배열.
- `profile`: 질문 유형.
- `difficulty`: 평가 난이도.
- `hit_chunk_ids`: Generation에 고정으로 제공할 공식문서 chunk ID.
- `expected_status`: `answered`, `no_evidence`, `filtered` 중 기대 상태.
- `must_include_groups`: 답변에 포함해야 하는 의미 묶음. 각 묶음 안에서는 하나의 표현만 포함해도 통과한다.
- `must_not_include`: 답변에 나오면 안 되는 무근거 단정·권유 표현.
- `required_citation_ids`: `answered` 응답이 반드시 인용해야 하는 핵심 chunk ID.
- `expected_missing_context_terms`: 개별 판단에 추가로 필요한 구체 확인 항목.

근거가 없는 케이스는 `no_evidence`, 질문과 무관한 chunk만 주어진 케이스는 `filtered`를 기대한다.
질문별 정답이나 확인 항목을 runtime prompt에 그대로 넣지 않고, 평가 데이터에만 유지한다.

### 지표

| 지표 | 계산 기준 | 높으면 의미하는 것 |
|---|---|---|
| `pass_rate` | 아래 모든 검사를 통과한 케이스 비율 | Generation 계약을 전반적으로 잘 지킴 |
| `status_match_rate` | `answered`·`no_evidence`·`filtered` 상태 일치율 | 근거 유무와 필터링 상태를 잘 구분함 |
| `citation_valid_rate` | 응답 citation ID가 제공된 고정 context 안에 있는 비율 | 존재하지 않는 근거 ID를 만들지 않음 |
| `required_citation_coverage` | `answered` 응답이 필수 chunk를 실제로 인용한 비율 | 핵심 근거를 빠뜨리지 않음 |
| `must_include_coverage` | 필수 의미 묶음을 모두 포함한 비율 | 질문에 필요한 핵심 내용을 포함함 |
| `must_not_include_clean_rate` | 금지 표현이 하나도 없는 비율 | 권유와 무근거 단정을 피함 |
| `missing_context_coverage` | 필요한 추가 확인 항목을 모두 남긴 비율 | 개별 판단의 한계를 구체적으로 설명함 |
| `numeric_grounding_rate` | 답변 숫자가 질문 또는 인용 근거에 모두 존재하는 비율 | 근거 없는 기간·금액·비율을 만들지 않음 |

`numeric_grounding_rate`는 답변의 숫자를 질문, 인용 source 제목·citation label·chunk 본문과 대조한다.
목록 번호처럼 의미 없는 번호는 검사에서 제외한다.

Generation 평가는 의미 유사도, embedding, LLM judge를 사용하지 않는다.
결과를 재현하고 실패 이유를 바로 확인하기 위한 명시적 contract 검사다.
따라서 `must_include_groups`에 없는 올바른 표현은 false negative가 될 수 있으므로 실패 답변은 사람이 함께 검토한다.

### 실행

유닛 테스트는 실제 OpenAI API를 호출하지 않는다.
live 평가는 `OPENAI_API_KEY`가 있는 환경에서 명시적으로 실행한다.

```bash
cd backend
PYTHONPATH=. uv run python app/services/rag/official/evaluation/generation.py --show-passing
```

## 최근 기준 결과

2026-07-15에 현재 데이터셋으로 측정한 결과다.
수치는 모델, 공식문서 index, 데이터베이스 상태가 바뀌면 함께 달라질 수 있다.

### Retrieval

| 실행 경로 | 전체 통과 | Positive Recall@5 | Precision@5 | MRR | nDCG@5 | Negative no-hit | 평균 지연 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 오프라인 Hashing | 26/72 | 0.481 | 0.096 | 0.305 | 0.318 | 0/18 | 0.166초 |
| 운영 pgvector | 43/72 | 0.796 | 0.178 | 0.646 | 0.643 | 0/18 | 1.052초 |

운영 검색은 positive 질문에서 관련 근거를 찾는 능력은 유지하지만, negative 질문에서도 항상 결과를 반환한다.
이는 현재 설계상 예상된 결과다. Official RAG retrieval은 공식문서 후보 검색을 담당하고, out-of-scope 질문 거절은 상위 QA 전체 라우터가 맡는다.

따라서 `negative_no_hit_rate`는 현재 retrieval 품질 목표라기보다, 상위 라우터 없이 검색기만 실행했을 때 생기는 한계를 보여주는 진단 지표로 해석한다.

### Generation

| 지표 | 결과 |
|---|---:|
| 전체 통과 | 52/60 (0.867) |
| 상태 일치 | 0.950 |
| citation ID 유효성 | 1.000 |
| 필수 인용 충족 | 0.950 |
| 필수 의미 포함 | 0.867 |
| 금지 표현 없음 | 1.000 |
| 부족한 정보 포함 | 1.000 |
| 숫자 grounding | 1.000 |

남은 실패는 필수 의미 일부 누락과, 관련 근거가 있어도 citation을 내지 않아 `filtered`가 되는 경우에 집중되어 있다.

## 과적합 방지 원칙

- 평가 질문별 정답 문구나 고정 숫자를 runtime prompt에 복사하지 않는다.
- 같은 시나리오에 최소 두 가지 질문 표현을 둔다.
- prompt나 검색 로직을 조정할 때 한 사례만 고치는 전용 규칙을 추가하지 않는다.
- 평가셋 실패를 완화할 때 실제 답변 오류와 문자열 matcher의 false negative를 구분한다.
- 저장소에 포함된 평가셋은 회귀 테스트로 사용한다. 최종 일반화 성능을 판단할 때는 개발 중 열어보지 않는 별도 blind holdout을 사용한다.
- 평가셋에는 실제 이름, 연락처, 주민등록번호, 이메일, 증권번호 같은 개인정보를 넣지 않는다.
