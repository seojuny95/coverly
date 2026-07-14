# Official RAG 평가

이 문서는 공식문서 RAG의 retrieval 평가와 generation 평가가 무엇을 보는지 정리한다.
두 평가는 일부 타입을 공유하지만 원인을 분리하기 위해 서로 다른 데이터셋과 실행 경로를 쓴다.

## Retrieval 평가

Retrieval 평가는 [retrieval_dataset.json](retrieval_dataset.json)의 질문을 검색기에 넣고, 검색 결과에 기대한 공식문서 source와 핵심 문구가 포함되는지 확인한다.

### 지표

| 지표 | 보는 대상 | 질문 | 높으면 의미하는 것 |
|---|---|---|---|
| `Recall@K` | 정답을 얼마나 안 놓쳤는지 | `정답을 K개 안에 잘 포함시켰나?` | 필요한 문서를 많이 찾아옴 |
| `Precision@K` | 가져온 결과의 순도 | `K개 중 쓸만한 문서가 얼마나 되나?` | 잡문서가 적음 |
| `MRR` | 첫 정답의 위치 | `첫 정답이 얼마나 앞에 나오나?` | 랭킹이 좋음 |

### 현재 구현 기준

현재 official RAG retrieval 평가는 `Recall@K`, `MRR`, `source_precision`, `평균 지연 시간`을 함께 본다.
또한 데이터셋이 문서 단위 관련성 라벨을 갖고 있지 않기 때문에, 엄밀한 `Precision@K` 대신 `source_precision`을 함께 본다.

- `Recall@K`: 상위 검색 결과 묶음 안에 `expected_source_ids`와 `expected_terms`가 모두 포함되면 통과로 본다.
- `expected_terms`는 `label + citation_label + text`를 합친 문자열에서 검사하며, 공백·대소문자·일부 기호 차이는 정규화해서 비교한다.
- `MRR`: 상위 결과를 앞에서부터 누적했을 때 `expected_source_ids`와 `expected_terms`가 처음 모두 충족되는 순위의 역수를 평균낸다.
- `source_precision`: 상위 결과 중 기대 source에서 온 chunk 비율이다. 잡 source가 얼마나 섞이는지 보는 보조 지표다.
- `평균 지연 시간`: 평가셋 전체를 처리한 시간을 케이스 수로 나눈 값이다. retrieval 개선이 응답 시간을 얼마나 늘리거나 줄이는지 본다.

`source_precision`은 관련 chunk 라벨이 아니라 source 라벨만 사용하므로, 일반적인 `Precision@K`보다 느슨하다.
정밀한 `Precision@K`가 필요하면 평가셋에 각 질문별 relevant chunk id 또는 relevant source+term 조합을 추가해야 한다.

### 해석

production 평가에서 `Recall@K`가 높고 `MRR`이 낮으면 정답이 검색 결과 안에는 있지만 앞쪽에 충분히 안정적으로 나오지 않는다는 뜻이다.
`source_precision`이 낮으면 질문과 무관한 공식문서 source가 상위 결과에 많이 섞인다는 뜻이다.
`평균 지연 시간`이 높으면 retrieval 품질이 조금 올라가더라도 운영 경로에 넣기 어렵다는 뜻이다.

따라서 retrieval 개선은 다음 순서로 본다.

1. evaluation false negative를 줄이기 위해 매칭 기준과 데이터셋을 먼저 점검한다.
2. pgvector 후보 위에서 hybrid ranking을 튜닝한다.
3. 청크 분할이 source/조항 경계를 흐리는 케이스를 보정한다.

## Generation 평가

Generation 평가는 [generation_dataset.json](generation_dataset.json)에 지정된 고정 근거 chunk를 `answer_official_question()`에 넣고, 최종 답변이 계약을 지키는지 확인한다.
이 평가는 retrieval을 타지 않는다.
따라서 점수가 낮으면 검색 품질보다 prompt, output contract, 답변 후처리 문제를 먼저 의심한다.
공식자료 RAG prompt는 사용하는 코드 가까이에 있는 [rag_answer_prompt.md](../rag_answer_prompt.md)에 둔다.

### 데이터셋

각 케이스는 다음 필드를 가진다.

- `question`: 사용자 질문.
- `hit_chunk_ids`: generation에 고정으로 넣을 공식문서 chunk id.
- `expected_status`: 기대 응답 상태. 현재는 `answered`와 `no_evidence`를 쓴다.
- `must_include_groups`: 답변 본문에 포함되어야 하는 핵심 의미 묶음. 각 묶음 안에서는 하나만 포함되어도 통과한다.
- `must_not_include`: 답변 본문에 나오면 안 되는 단정·권유 표현.
- `required_citation_ids`: 반드시 인용해야 하는 근거 chunk id.
- `expected_missing_context_terms`: 개별 판단에 추가로 필요한 정보.

### 지표

| 지표 | 보는 대상 | 높으면 의미하는 것 |
|---|---|---|
| `pass_rate` | 모든 체크를 통과한 케이스 비율 | 현재 prompt와 contract가 평가셋 요구를 전반적으로 만족함 |
| `status_match_rate` | `answered`/`no_evidence` 상태 | 근거 있음·없음 상태를 잘 구분함 |
| `citation_valid_rate` | 응답 citation id | 없는 citation을 만들지 않음 |
| `required_citation_coverage` | 필수 근거 인용 | 핵심 근거를 실제로 사용함 |
| `must_include_coverage` | 답변 핵심 표현 | 질문에 필요한 내용을 답변에 포함함 |
| `must_not_include_clean_rate` | 금지 표현 | 권유·무근거 단정 표현을 피함 |
| `missing_context_coverage` | 부족한 정보 구체화 | 개별 판단에 필요한 자료를 구체적으로 남김 |

### 현재 구현 기준

Generation 평가는 의미 유사도, embedding, LLM judge를 쓰지 않는다.
의도적으로 단순한 contract check만 사용한다.
`must_include_groups`는 같은 의미의 표현을 묶어서 문자열 평가의 억울한 실패를 줄인다.
다만 묶음에 없는 표현으로 답하면 의미상 맞아도 실패할 수 있다.

`missing_context`는 답변 생성 후 후처리에서 한 번 더 정리한다.
후처리는 포괄 문구와 중복만 제거한다.
질문 유형별로 어떤 확인 항목을 남길지는 runtime 휴리스틱이 아니라 prompt가 책임진다.

### 실행

유닛 테스트는 실제 OpenAI API를 호출하지 않는다.
live generation 평가는 `OPENAI_API_KEY`가 있는 환경에서 명시적으로 실행한다.

```bash
PYTHONPATH=. uv run python app/services/rag/official/evaluation/generation.py --show-passing
```

현재 작업트리에서 원본 프로젝트의 로컬 env를 임시로 재사용할 때는 다음처럼 실행했다.

```bash
set -a
source /Users/seojun/Desktop/project/coverly/backend/.env
set +a
PYTHONPATH=. uv run python app/services/rag/official/evaluation/generation.py --show-passing
```

### 현재 해석

최근 live 평가에서는 세 단계를 나눠 확인했다.

| 단계 | 통과 | 핵심 변화 |
|---|---:|---|
| 의미 그룹 평가 도입 | 11/12 | 표현 차이로 생기던 false negative가 줄었다. |
| 숫자·예외 보존 prompt 추가 | 11/12 | 청약철회 `30일` 누락은 그대로 남았다. |
| 휴리스틱 제거 + prompt 중심 `missing_context` | 8/12 | runtime 규칙은 단순해졌지만, prompt만으로는 일부 확인 항목이 빠졌다. |
| 최신 retrieval 일부 재라벨링 | 8/12 | 실제 검색 결과에 더 가까운 고정 context로 맞췄지만 총점은 그대로였다. |
| `missing_context` 공백 차이 완화 + 질문별 확인 항목 보강 | 10/12 | evaluator의 억울한 실패를 줄이고 prompt에서 부족한 확인 항목을 더 직접적으로 유도했다. |

남은 실패는 주로 두 종류다.

- 실제 답변 누락: 청약 철회 답변에서 `30일` 조건을 빠뜨리는 경우처럼 근거 chunk 안의 예외·상한 조건을 충분히 반영하지 못한다.
- prompt만으로 부족한 정보 선택이 불안정한 경우: 도수치료는 `치료 기록`, `담보 조건`을 잘 남기지만, 고지의무 위반은 `위반 내용`, `보험금 지급사유`를 빠뜨릴 수 있다.
