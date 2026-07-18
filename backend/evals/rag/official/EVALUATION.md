# Official RAG 평가 개선 기록

이 문서는 Official RAG 평가를 어떻게 만들고 개선했는지 간단히 기록한다.
목표는 공식자료 RAG를 `extraction → retrieval → generation`으로 나누어 보고, 어느 단계가 깨졌는지 빠르게 찾는 것이다.

RAG e2e 평가는 포함한다.
다만 QA router/planner 평가는 포함하지 않는다.
범위 밖 질문을 최종 QA 응답에서 거절하는지는 이후 QA 기능이 안정된 뒤 별도 평가로 다룬다.

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
| 문서 타입별 chunker 분리 | 130/130 | 법령 XML, 표준약관, 자동차보험 표준상품설명서, 일반 소비자 안내자료를 별도 chunker로 나눴다. 자동차보험 설명서는 실제 섹션 제목 기준 label을 사용한다. |

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
| 문서 타입별 chunker 분리 및 운영 재인덱싱 | offline 44/54, production 48/54, accepted 0.889 | 법령/표준약관/자동차보험 설명서/일반 소비자 안내자료 chunker를 분리하고 Supabase index를 1,326개 chunk로 재생성했다. |

현재 운영 pgvector 기준 retrieval은 positive 48/54, accepted 0.889다.
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

## RAG E2E

RAG E2E는 official retrieval 결과를 그대로 official generation에 넣었을 때 최종 답변 계약이 지켜지는지 본다.
QA router, planner, 사용자 업로드 증권은 거치지 않는다.

### 평가셋 구성

- 총 150개 케이스.
- generation 평가셋 전체 60개와 retrieval 평가셋 전체 72개를 retrieval→generation으로 다시 실행한다.
- 별도 negative/out-of-scope 18개를 추가했다.
- 고지의무, 면책, 청약철회, 화재보험 계산, 대위권, 보험나이, 금융소비자보호, 보험업법, 상품명/의료리스크 정책, 개인계약 조회 불가, 실시간/의료/법률/투자 범위 밖 질문을 포함한다.
- 기본 실행은 OpenAI 호출 없이 deterministic extractive completer를 사용한다.
- live LLM은 `--live-generation` 옵션으로 별도 확인한다.
- E2E는 generation 계약 검증이 목적이라 핵심 근거 인용을 확인한다.
  다만 표준약관은 같은 조항 제목이 상품군별로 반복되므로, 같은 `standard_clause` 조항 제목은 대체 근거로 인정한다.

### 개선 기록

| 단계 | 결과 | 개선 내용 |
|---|---:|---|
| RAG E2E v1 baseline | 13/24, pass_rate 0.542 | 대표 시나리오만 골라 연결 smoke test로 시작했다. 부족한 지점을 충분히 드러내지 못했다. |
| RAG E2E broad baseline | 21/60, pass_rate 0.350 | generation 전체 시나리오로 확장했다. 실패는 필요한 chunk가 top-5에 없거나, 검색은 됐지만 추출형 답변이 필수 표현을 담지 못한 경우, negative/out-of-scope가 answered로 흐르는 경우다. |
| RAG E2E reliable baseline | 47/150, pass_rate 0.313 | generation 전체, retrieval 전체, extra negative를 합쳐 150개로 확장했다. negative/out-of-scope 거절과 retrieval miss가 더 명확히 드러난다. |
| 문서 타입별 chunker 분리 후 | 49/150, pass_rate 0.327 | 자동차보험 설명서 섹션 chunking과 표준약관 section citation 보강 후 retrieval_miss와 answer_missing이 각각 1건 줄었다. |
| E2E citation group 보정 | 51/150, pass_rate 0.340 | retrieval 평가셋의 대체 가능 chunk ID를 E2E에서 전부 필수로 보던 false negative를 줄였다. |
| hybrid 후보 폭/가중치 조정 | 63/150, pass_rate 0.420 | 후보 폭을 120으로 넓히고 BM25 비중을 0.60으로 올렸다. 표준약관 반복 조항은 같은 조항 제목이면 대체 근거로 인정했다. |

### 실패 분해

hybrid 후보 폭/가중치 조정 후 `63/150`의 실패는 다음 세 묶음이다.

| 실패군 | 건수 | 의미 |
|---|---:|---|
| answerability_status_mismatch | 42 | negative/out-of-scope 질문인데 offline extractive completer가 검색된 발췌문을 그대로 답변으로 만들어 `answered`가 된다. Retrieval 튜닝으로 해결할 문제가 아니다. |
| retrieval_miss | 22 | 필요한 핵심 citation chunk 또는 대체 가능한 표준약관 조항이 top-5 안에 없다. Chunking, ranking, rerank, corpus 품질을 봐야 한다. |
| answer_missing_required_content | 23 | 필요한 chunk는 검색됐지만 답변에 필수 내용이 빠진다. Context packing, prompt, citation coverage, 또는 offline completer 한계를 봐야 한다. |

키워드/단어 기반 scope gate는 사용하지 않는다.
Official RAG 개선은 검색 근거 품질, context 구성, citation grounding을 기준으로 한다.

### 폐기한 개선 실험

| 실험 | 결과 | 판단 |
|---|---:|---|
| RRF 상수 20 → 10 | E2E 47/150 → 53/150 | 수치는 조금 올랐지만 개선 폭이 작고 근본 병목을 해결하지 못해 폐기했다. |
| top-k 5 → 8, citation capacity 6 → 8 | retrieval_miss 37 → 29, E2E 47/150 유지 | 필요한 근거는 더 들어오지만 answer_missing이 24 → 32로 늘었다. Context noise가 늘어 폐기했다. |
| score cutoff | 미적용 | positive와 negative의 keyword/vector score 분포가 겹쳐 과차단 위험이 컸다. |

### 다음 개선 방향

1. `retrieval_miss`는 정답 chunk rank를 보고 나눈다.
   37건 중 15건은 정답 chunk가 6~10위에 있어 rerank/context selection 후보이고,
   나머지는 query-corpus mismatch나 chunking 문제를 봐야 한다.
2. `answer_missing_required_content`는 top-k를 무작정 늘리지 말고 context packing을 고쳐야 한다.
   필요한 조항의 뒤쪽 문장이 잘리지 않도록 chunk 내부 excerpt 선택 또는 section-aware packing을 검토한다.
3. `answerability_status_mismatch`는 retrieval 튜닝으로 해결하지 않는다.
   offline extractive completer가 negative에도 발췌문을 복사하는 한계가 있으므로,
   live generation 또는 별도 context sufficiency 평가로 분리해서 본다.

## 현재 상태 요약

| 영역 | 최신 결과 | 상태 |
|---|---:|---|
| Extraction | 130/130 | component 평가 구축됨 |
| Retrieval offline | 46/54, accepted 0.852 | 빠른 회귀 확인 가능 |
| Retrieval production | 49/54, accepted 0.907 | 운영 index 기준 확인 완료 |
| Generation | 60/60 | 고정 context 답변 계약 확인 가능 |
| RAG E2E offline | 63/150, pass_rate 0.420 | retrieval miss와 평가 false negative 일부 개선 |

Official RAG의 component 평가는 v1 수준으로 구축되었다.
남은 큰 작업은 official E2E 실패 케이스를 retrieval 개선과 answer context 압축 개선으로 나눠 처리하고, QA 기능이 안정된 뒤 `router/e2e 평가`와 `blind holdout`을 추가하는 것이다.
