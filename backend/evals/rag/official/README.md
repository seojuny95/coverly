# Official RAG 평가

이 문서는 공식문서 RAG의 Extraction, Retrieval, Generation 품질을 서로 분리해 평가하는 기준을 정리한다.
Extraction은 공식 PDF/XML을 citation 가능한 chunk로 뽑는 능력, Retrieval은 필요한 근거 chunk를 찾는 능력, Generation은 고정된 근거에서 안전하고 충실한 답변을 만드는 능력을 본다.

Extraction 평가셋은 **120개 대표 chunk 케이스**로 구성한다.
Retrieval 평가셋은 **33개 시나리오 × 질문 표현 2개 = 66개 케이스**로 구성한다.
Generation 평가셋은 **30개 시나리오 × 질문 표현 2개 = 60개 케이스**로 구성한다.
같은 사실이나 질문 의도를 서로 다른 표현으로 물어 단순 키워드 일치에만 유리한 평가가 되지 않도록 한다.

공식문서 chunking은 문서 타입별로 나눈다. 법령 XML, 표준약관, 자동차보험 표준상품설명서, 일반 소비자 안내자료가 서로 다른 구조를 갖기 때문이다. 각 chunker는 문서 구조를 해석해 공통 `RagChunk` 형식으로만 합류하며, 사용자 질문의 키워드로 검색 경로를 분기하지 않는다.

## Extraction 평가

Extraction 평가는 [extraction_dataset.json](extraction_dataset.json)에 지정된 공식문서 chunk가 현재 loader/chunker 결과에 그대로 존재하는지 확인한다.
Retrieval이나 Generation을 실행하지 않고, 공식 source 원문에서 만들어진 chunk의 metadata와 본문만 본다.

### 데이터셋

각 케이스는 다음 필드를 가진다.

- `id`: 케이스 식별자.
- `case_type`: `curated` 또는 `broad_regression`. `curated`는 사람이 지정한 source/label/page/text 조건으로 chunk 존재를 확인하고, `broad_regression`은 기존 chunk ID의 회귀를 확인한다.
- `source_id`: 공식 source ID.
- `chunk_id`: `broad_regression` 케이스에서 사람이 확인한 기대 chunk ID. `curated` 케이스는 chunk ID에 의존하지 않는다.
- `expected_source_category`: `standard_clause`, `consumer_guide`, `law` 같은 source category.
- `expected_label`: citation에 사용할 조항/섹션 label.
- `expected_citation_contains`: citation label에 포함되어야 하는 문자열.
- `expected_page_start`, `expected_page_end`: chunk page range.
- `must_include`: retrieval embedding 입력(`source_title + label + text`)에 포함되어야 하는 핵심 문자열.

현재 데이터셋은 표준약관 62개, 자동차보험 표준상품설명서 9개, 찾기 쉬운 생활법령정보 보험계약자 9개, 보험업법 XML 25개, 금융소비자보호법 XML 15개 케이스로 구성한다.
이 중 47개는 `curated`, 73개는 `broad_regression`이다.

### 지표

| 지표 | 계산 기준 | 높으면 의미하는 것 |
|---|---|---|
| `pass_rate` | 모든 check를 통과한 케이스 비율 | 공식문서 extraction 계약이 유지됨 |
| `chunk_found_rate` | 기대 chunk ID가 존재하는 비율 | chunk ID가 사라지거나 바뀌지 않음 |
| `metadata_match_rate` | source/category/label/page가 일치하는 비율 | citation metadata가 안정적임 |
| `citation_match_rate` | citation label 필수 문자열을 포함한 비율 | 사용자에게 보여줄 근거명이 유지됨 |
| `text_coverage_rate` | 본문 필수 문자열을 포함한 비율 | chunk 본문이 누락되지 않음 |

### 실행

```bash
cd backend
uv run python -m evals.rag.official.extraction --show-passing
```

## Retrieval 평가

Retrieval 평가는 [retrieval_dataset.json](retrieval_dataset.json)의 질문을 검색기에 넣고 상위 5개 결과를 평가한다.
사람이 확인한 정확한 `relevant_chunk_ids`를 회귀 라벨로 유지하되, corpus 확장 이후 동일한 의미의 공식 근거를 허용하기 위해 `accepted_evidence` 조건도 함께 사용한다.

### 데이터셋

각 시나리오는 다음 필드를 가진다.

- `id`: 시나리오 식별자.
- `questions`: 같은 의도를 서로 다르게 표현한 질문 배열. 현재 각 시나리오당 2개다.
- `profile`: `term_explain`, `claim_check`, `consumer_protection`, `out_of_scope` 중 하나다.
- `difficulty`: `easy`, `medium`, `hard` 중 하나다.
- `relevant_chunk_ids`: 사람이 확인한 대표 정답 chunk ID. exact 회귀 확인에 사용한다.
- `accepted_evidence`: 동일한 답변 근거로 허용할 공식 source/category와 필수 문자열 조건. corpus 확장으로 대체 공식 근거가 검색될 수 있는 경우를 평가한다.
- `expected_no_hits`: 공식문서 검색 범위 밖 질문의 진단용 라벨이다. retrieval 품질 gate에는 포함하지 않는다.

현재 66개 케이스 중 48개는 관련 근거가 있는 positive 케이스이고, 18개는 날씨·기기 지원·사용자 개인 계약값·뉴스·주가·병원 예약·앱 계정·개인 보장금액·실시간 정보처럼 공식문서로 답할 수 없는 negative 케이스다.

### 지표

모든 `@K` 지표는 현재 `K=5`로 계산한다.

| 지표 | 계산 기준 | 높으면 의미하는 것 |
|---|---|---|
| `pass_rate` | positive 케이스 중 exact chunk 또는 `accepted_evidence` 조건을 만족한 비율 | retrieval이 답변 가능한 질문에서 필요한 공식 근거를 찾음 |
| `accepted_pass_rate` | positive 케이스 중 exact chunk 또는 `accepted_evidence` 조건을 만족한 비율 | 같은 의미의 공식 근거를 포함해 필요한 근거를 찾음 |
| `Recall@5` | positive 케이스 중 exact `relevant_chunk_ids`를 하나 이상 찾은 비율 | 대표 chunk ID 회귀를 덜 놓침 |
| `accepted_recall@5` | positive 케이스 중 exact 또는 accepted 근거를 하나 이상 찾은 비율 | corpus 확장 후 대체 공식 근거까지 포함해 덜 놓침 |
| `Precision@5` | 상위 5개 결과 중 관련 chunk의 비율을 positive 케이스 전체에서 평균 | 불필요한 chunk가 적음 |
| `MRR` | positive 케이스에서 첫 관련 chunk 순위 역수의 평균 | 관련 근거가 앞쪽에 배치됨 |
| `nDCG@5` | 관련 chunk의 순위별 이득을 이상적인 순서와 비교 | 여러 관련 근거의 전반적인 랭킹이 좋음 |
| `diagnostic_negative_no_hit_rate` | negative 케이스에서 검색 결과가 하나도 없었던 비율 | 검색기가 범위 밖 질문에도 후보를 반환하는지 참고 확인함 |
| `average_latency_seconds` | 전체 검색 시간을 케이스 수로 나눈 값 | 검색 응답이 빠름 |

`Recall@5`, `accepted_recall@5`, `Precision@5`, `MRR`, `nDCG@5`는 negative 케이스를 제외한 positive 케이스를 분모로 사용한다.
`pass_rate`와 `accepted_pass_rate`도 positive 케이스만 분모로 사용한다.
negative 케이스는 retrieval이 아니라 상위 QA router/e2e의 답변 가능성 판단에서 품질 gate로 평가한다.

### 실행 경로

오프라인 평가는 공식문서 chunk에 `HashingEmbedder`를 적용한 인메모리 경로를 사용한다.
빠르고 결정적이지만 운영 임베딩 품질을 대표하지 않으므로 ranking 회귀를 빠르게 확인하는 용도다.

```bash
cd backend
PYTHONPATH=. uv run python - <<'PY'
from evals.rag.official.retrieval import evaluate_retrieval

report = evaluate_retrieval()
print(
    report.pass_rate,
    report.accepted_pass_rate,
    report.recall,
    report.accepted_recall,
    report.precision_at_k,
    report.mrr,
    report.ndcg_at_k,
    report.diagnostic_negative_no_hit_rate,
    report.average_latency_seconds,
)
PY
```

운영 평가는 OpenAI embedding과 실제 pgvector index를 사용한다.
`OPENAI_API_KEY`, `DATABASE_URL`과 최신 공식문서 index가 필요하며 유닛 테스트에서는 실행하지 않는다.

```bash
cd backend
PYTHONPATH=. uv run python - <<'PY'
from evals.rag.official.retrieval import evaluate_retrieval

report = evaluate_retrieval(production=True)
print(
    report.pass_rate,
    report.accepted_pass_rate,
    report.recall,
    report.accepted_recall,
    report.precision_at_k,
    report.mrr,
    report.ndcg_at_k,
    report.diagnostic_negative_no_hit_rate,
    report.average_latency_seconds,
)
PY
```

### 결과 해석

- `Recall@5`가 낮고 `accepted_recall@5`가 높으면 대표 chunk ID는 놓쳤지만 의미상 허용 가능한 공식 근거는 찾은 것이다.
- `accepted_recall@5`가 낮으면 query 표현, embedding, 후보 검색 또는 chunk 라벨을 먼저 확인한다.
- `Recall@5`는 높고 `MRR`이나 `nDCG@5`가 낮으면 정답은 찾지만 순위가 뒤쪽이라는 뜻이다.
- `Precision@5`가 낮으면 Generation에 불필요한 context가 많이 전달될 수 있다.
- `diagnostic_negative_no_hit_rate`가 낮으면 검색기가 범위 밖 질문에도 후보를 반환한다는 뜻이다. 현재 Official RAG retrieval은 라우팅을 맡지 않으므로, 범위 밖 질문 거절은 상위 QA 라우터에서 별도로 평가해야 한다.
- 오프라인과 운영 결과 차이가 크면 HashingEmbedder 결과를 운영 품질로 해석하지 않는다.

## Generation 평가

Generation 평가는 [generation_dataset.json](generation_dataset.json)에 지정된 고정 근거 chunk를 [answer.py](../../../app/rag/official/answer.py)의 `answer_official_question()`에 직접 전달한다.
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
uv run python -m evals.rag.official.generation --show-passing
```

## 최근 기준 결과

2026-07-15부터 2026-07-19까지 Retrieval/Generation/Extraction 데이터셋으로 측정한 결과다.
2026-07-20에 보험약관 개선 로드맵을 런타임 RAG에서 제외하면서 extraction은 120개, retrieval은 66개 케이스로 조정됐다.
수치는 모델, 공식문서 index, 데이터베이스 상태가 바뀌면 함께 달라질 수 있다.

### Retrieval

| 실행 경로 | Positive 통과 | Accepted pass | Exact Recall@5 | Accepted Recall@5 | Precision@5 | MRR | nDCG@5 | Diagnostic negative no-hit | 평균 지연 | 결정 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 오프라인 Hashing 기존 | 25/54 | - | 0.463 | - | 0.093 | 0.262 | 0.282 | 0/18 | 0.180초 | exact chunk ID만 정답으로 보아 corpus 확장에 취약 |
| 오프라인 Hashing accepted 기준 추가 | 37/54 | 0.685 | 0.463 | 0.685 | 0.093 | 0.262 | 0.282 | 0/18 | 0.194초 | 대체 공식 근거를 평가 가능하게 함 |
| 오프라인 Hashing 한국어 ngram 개선 후 | 44/54 | 0.815 | 0.704 | 0.815 | 0.144 | 0.365 | 0.421 | 0/18 | 0.442초 | 복합어·띄어쓰기 차이를 보강 |
| 문서 타입별 chunker 분리 후 | 44/54 | 0.815 | 0.704 | 0.815 | 0.148 | 0.361 | 0.422 | 0/18 | 0.447초 | 표준약관/자동차보험 설명서 chunker를 분리하고 자동차보험 설명서 섹션 chunk를 세분화 |
| hybrid 후보 폭/가중치 조정 | 46/54 | 0.852 | 0.722 | 0.852 | 0.148 | 0.432 | 0.459 | 0/18 | 0.479초 | 후보 폭을 120으로 넓히고 BM25 비중을 0.60으로 조정 |
| 운영 pgvector 기존 | 43/54 | - | 0.796 | - | 0.178 | 0.646 | 0.643 | 0/18 | 1.052초 | 실제 pgvector/OpenAI embedding 기준 참고값 |
| 운영 pgvector accepted 기준 재측정 | 49/54 | 0.907 | 0.815 | 0.907 | 0.185 | 0.654 | 0.665 | 0/18 | 1.120초 | 운영 index에서도 accepted 기준 개선 확인 |
| 운영 pgvector 문서 타입별 chunker 재인덱싱 후 | 48/54 | 0.889 | 0.833 | 0.889 | 0.185 | 0.636 | 0.651 | 0/18 | 1.049초 | Supabase index를 1,326개 chunk로 재생성하고 legacy 테이블을 제거 |
| 운영 pgvector hybrid 후보 폭/가중치 조정 | 49/54 | 0.907 | 0.852 | 0.907 | 0.189 | 0.662 | 0.673 | 0/18 | 1.338초 | 운영 index는 재생성 없이 retrieval 후보 폭과 BM25 비중만 조정 |
| 운영 pgvector 의미 기반 context selection | 54/54 | 1.000 | 0.981 | 1.000 | 0.421 | 0.814 | 0.824 | 17/18 | 3.560초 | hybrid/RRF 후보를 LLM이 질문과 직접 비교하고 선택하지 않은 context는 제외한다. 품질은 개선됐지만 LLM 호출로 지연이 늘어남 |

### Extraction

| 단계 | 데이터셋 | 전체 통과 | curated | broad | chunk 존재 | metadata | citation | text | 결정 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Baseline | 50 | 50/50 (1.000) | - | - | 1.000 | 1.000 | 1.000 | 1.000 | smoke set은 통과했지만 표준약관/법령 long-tail이 부족 |
| 확장 직후 | 100 | 98/100 (0.980) | - | - | 1.000 | 1.000 | 1.000 | 0.980 | continuation chunk는 label이 metadata에만 있어 text check에서 false negative 발생 |
| embedding 기준 개선 후 | 100 | 100/100 (1.000) | - | - | 1.000 | 1.000 | 1.000 | 1.000 | text check 기준을 실제 retrieval embedding 입력과 맞춤 |
| curated/broad 분리 후 | 100 | 100/100 (1.000) | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 20개 curated 케이스는 chunk ID 없이 source/label/page/text 조건으로 평가 |
| 공식 소비자 안내자료 추가 후 | 110 | 110/110 (1.000) | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 자동차보험 표준상품설명서와 생활법령정보 보험계약자 PDF를 corpus에 추가하고 curated 10개를 보강 |
| curated hard case 보강 후 | 130 | 130/130 (1.000) | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 실손·자동차·화재·배상책임·청구/해지 중심 curated 20개를 추가해 독립 평가 비중을 50개로 확대 |
| 문서 타입별 chunker 분리 후 | 130 | 130/130 (1.000) | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 법령/표준약관/자동차보험 설명서/일반 소비자 안내자료 chunker를 분리하고 자동차보험 설명서 label fixture를 실제 섹션 기준으로 갱신 |

Extraction 점수는 회귀 안정성을 뜻한다. 특히 `broad_regression`은 현재 corpus의 chunk ID 보존을 확인하는 성격이 강하므로, 일반화된 extraction 품질 점수로 해석하지 않는다.

기존 hybrid 검색은 negative 질문에서도 항상 결과를 반환했지만, 의미 기반 context selection 적용 후에는 18개 중 17개를 근거 없음으로 판정했다.
`diagnostic_negative_no_hit_rate`는 retrieval 단계의 context sufficiency 진단으로 추적하되, out-of-scope 질문을 최종 거절하는 책임은 상위 QA 전체 라우터에 둔다.

### Generation

| 단계 | 전체 통과 | 상태 일치 | citation ID 유효성 | 필수 인용 | 필수 의미 | 금지 표현 없음 | 부족한 정보 | 숫자 grounding | 결정 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Baseline | 52/60 (0.867) | 0.950 | 1.000 | 0.950 | 0.867 | 1.000 | 1.000 | 1.000 | citation label을 id 대신 반환하는 응답과 좁은 matcher가 주 실패 원인 |
| citation alias·matcher 1차 개선 | 57/60 (0.950) | 0.983 | 1.000 | 0.983 | 0.950 | 1.000 | 1.000 | 1.000 | citation label을 chunk id로 정규화하고 명확한 동의어를 보강 |
| matcher 2차 개선 | 59/60 (0.983) | 1.000 | 1.000 | 1.000 | 0.983 | 1.000 | 1.000 | 1.000 | 남은 false negative 표현을 보강 |
| citation alias 확장 후 | 60/60 (1.000) | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 조문 label·짧은 조문명 alias를 허용해 live 응답 변동성 완화 |

실패는 답변 내용 오류보다 citation 식별자 형식 차이와 `must_include_groups`의 표현 폭 부족에 집중되어 있었다.
runtime prompt에 평가 정답을 넣지 않고, 후처리의 근거 ID 정규화와 평가 matcher의 동의어 보강으로 개선했다.

## 과적합 방지 원칙

- 평가 질문별 정답 문구나 고정 숫자를 runtime prompt에 복사하지 않는다.
- 같은 시나리오에 최소 두 가지 질문 표현을 둔다.
- prompt나 검색 로직을 조정할 때 한 사례만 고치는 전용 규칙을 추가하지 않는다.
- 평가셋 실패를 완화할 때 실제 답변 오류와 문자열 matcher의 false negative를 구분한다.
- 저장소에 포함된 평가셋은 회귀 테스트로 사용한다. 최종 일반화 성능을 판단할 때는 개발 중 열어보지 않는 별도 blind holdout을 사용한다.
- 평가셋에는 실제 이름, 연락처, 주민등록번호, 이메일, 증권번호 같은 개인정보를 넣지 않는다.
