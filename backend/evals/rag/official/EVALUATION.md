# Official RAG 평가 개선 기록

이 문서는 Official RAG 평가를 어떻게 만들고 개선했는지 간단히 기록한다.
목표는 공식자료 RAG를 `extraction → retrieval → generation`으로 나누어 보고, 어느 단계가 깨졌는지 빠르게 찾는 것이다.

아직 e2e/router 평가는 포함하지 않는다.
범위 밖 질문을 최종 답변에서 거절하는지는 이후 QA 기능이 안정된 뒤 별도 평가로 다룬다.

## Extraction

Extraction은 공식 PDF/XML 원문이 citation 가능한 chunk로 잘 들어오는지 본다.
Retrieval이나 LLM 답변은 실행하지 않고, chunk의 source/category/label/page/text만 확인한다.

### 평가셋 구성

- 총 130개 케이스.
- 50개는 `curated` 케이스다. 사람이 source, label, page, 필수 문구를 지정한다.
- 80개는 `broad_regression` 케이스다. 기존 chunk ID가 유지되는지 확인한다.
- 표준약관, 자동차보험 표준상품설명서, 생활법령정보, 보험업법, 금융소비자보호법을 포함한다.

### 개선 기록

| 단계 | 결과 | 개선 내용 |
|---|---:|---|
| Baseline | 50/50 | smoke set으로 기본 chunk 추출이 깨지지 않는지 확인했다. |
| 평가셋 100개 확장 | 98/100 | 표준약관·법령 long-tail을 늘렸다. 일부 continuation chunk가 false negative를 만들었다. |
| embedding 기준 개선 | 100/100 | text check 기준을 실제 retrieval embedding 입력과 맞췄다. |
| curated/broad 분리 | 100/100 | chunk ID에 덜 의존하는 curated 평가를 분리했다. |
| 공식 소비자 안내자료 추가 | 110/110 | 자동차보험 표준상품설명서와 생활법령정보 자료를 추가했다. |
| hard case 보강 | 130/130 | 실손·자동차·화재·배상책임·청구/해지 중심 curated 케이스를 50개까지 늘렸다. |

현재 extraction 평가는 회귀 안정성 확인용으로는 충분하다.
다만 `broad_regression`은 현재 corpus의 chunk ID 보존 성격이 강하므로 일반화 성능으로 보지는 않는다.

## Retrieval

Retrieval은 질문에 필요한 공식 근거가 top-5 안에 들어오는지 본다.
정확한 chunk ID뿐 아니라, 같은 의미의 다른 공식 근거도 인정하도록 `accepted_evidence`를 추가했다.

### 평가셋 구성

- 총 36개 시나리오, 질문 표현 2개씩 72개 케이스.
- 54개는 관련 근거가 있는 positive 케이스다.
- 18개는 공식문서로 답할 수 없는 negative 케이스다.
- negative는 retrieval 품질 gate가 아니라 진단 지표로만 본다.
- `relevant_chunk_ids`는 exact 회귀 확인용이다.
- `accepted_evidence`는 같은 의미의 공식 근거를 인정하기 위한 조건이다.

### 개선 기록

| 단계 | 결과 | 개선 내용 |
|---|---:|---|
| Offline baseline | 25/54 | exact chunk ID만 정답으로 봤다. corpus가 커지면 좋은 대체 근거도 실패로 잡혔다. |
| accepted 기준 추가 | 37/54, accepted 0.685 | 대체 공식 근거를 인정하도록 평가 기준을 넓혔다. |
| 한국어 n-gram 개선 | 44/54, accepted 0.815 | `중복계약`, `특별이익`처럼 붙임·띄어쓰기 차이를 줄이기 위해 token-level n-gram을 추가했다. |
| 운영 pgvector 재측정 | 49/54, accepted 0.907 | 실제 OpenAI embedding + pgvector index에서도 개선을 확인했다. |

현재 운영 pgvector 기준 retrieval은 꽤 안정적이다.
다만 precision@5는 0.185라 불필요한 context가 섞일 수 있고, 이는 generation/e2e에서 계속 확인해야 한다.

`negative_no_hit`은 대표 지표에서 제외했다.
검색기가 범위 밖 질문에도 관련 후보를 반환하는 것은 자연스러울 수 있으므로, 최종 거절은 QA router/e2e에서 평가한다.

## Generation

Generation은 고정된 공식 근거 chunk를 넣었을 때 답변이 안전하고 충실한지 본다.
Retrieval을 거치지 않으므로 실패하면 prompt, citation 처리, 답변 후처리, 평가 matcher 중 하나를 먼저 의심한다.

### 평가셋 구성

- 총 30개 시나리오, 질문 표현 2개씩 60개 케이스.
- 대부분은 `answered`를 기대하는 공식자료 답변 케이스다.
- 일부는 `no_evidence` 또는 `filtered`를 기대한다.
- `must_include_groups`로 답변에 필요한 의미를 확인한다.
- `must_not_include`로 무근거 단정, 판매 권유 표현을 막는다.
- `required_citation_ids`로 핵심 근거 인용을 확인한다.
- 숫자는 질문 또는 인용 근거 안에 있는 숫자인지 검사한다.

### 개선 기록

| 단계 | 결과 | 개선 내용 |
|---|---:|---|
| Baseline | 52/60 | 답변 내용은 대체로 맞았지만 citation label을 chunk ID 대신 반환하거나 matcher가 좁아서 실패했다. |
| citation alias 1차 개선 | 57/60 | citation label을 selected chunk ID로 정규화했다. 명확한 동의어도 평가셋에 보강했다. |
| matcher 2차 개선 | 59/60 | 의미는 맞지만 표현이 달라 실패한 케이스를 줄였다. |
| citation alias 확장 | 60/60 | 조문 label, 짧은 조문명도 selected chunk 안에서만 citation alias로 인정했다. |

중요한 점은 runtime prompt에 평가 정답을 넣지 않았다는 것이다.
개선은 두 가지에만 집중했다.

- 모델이 근거 ID 대신 사람이 읽는 조문명을 반환해도 같은 selected context 안에서 안전하게 매핑한다.
- 평가 matcher는 실제 근거와 답변에서 확인된 동의 표현만 추가한다.

## 현재 상태 요약

| 영역 | 최신 결과 | 상태 |
|---|---:|---|
| Extraction | 130/130 | component 평가 구축됨 |
| Retrieval offline | 44/54, accepted 0.815 | 빠른 회귀 확인 가능 |
| Retrieval production | 49/54, accepted 0.907 | 운영 index 기준 확인 완료 |
| Generation | 60/60 | 고정 context 답변 계약 확인 가능 |

Official RAG의 component 평가는 v1 수준으로 구축되었다.
남은 큰 작업은 QA 기능이 안정된 뒤 `router/e2e 평가`와 `blind holdout`을 추가하는 것이다.
