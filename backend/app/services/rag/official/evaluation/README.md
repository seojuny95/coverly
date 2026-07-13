# Retrieval 평가

이 문서는 공식문서 RAG의 retrieval 평가 지표가 무엇을 의미하는지 정리한다.
현재 평가는 [retrieval_dataset.json](retrieval_dataset.json)의 질문을 검색기에 넣고, 검색 결과에 기대한 공식문서 source와 핵심 문구가 포함되는지 확인한다.

## 지표

| 지표 | 보는 대상 | 질문 | 높으면 의미하는 것 |
|---|---|---|---|
| `Recall@K` | 정답을 얼마나 안 놓쳤는지 | `정답을 K개 안에 잘 포함시켰나?` | 필요한 문서를 많이 찾아옴 |
| `Precision@K` | 가져온 결과의 순도 | `K개 중 쓸만한 문서가 얼마나 되나?` | 잡문서가 적음 |
| `MRR` | 첫 정답의 위치 | `첫 정답이 얼마나 앞에 나오나?` | 랭킹이 좋음 |

## 현재 구현 기준

현재 official RAG retrieval 평가는 `Recall@K`와 `MRR`을 계산한다.
또한 데이터셋이 문서 단위 관련성 라벨을 갖고 있지 않기 때문에, 엄밀한 `Precision@K` 대신 `source_precision`을 함께 본다.

- `Recall@K`: 상위 검색 결과 묶음 안에 `expected_source_ids`와 `expected_terms`가 모두 포함되면 통과로 본다.
- `MRR`: 상위 결과를 앞에서부터 누적했을 때 `expected_source_ids`와 `expected_terms`가 처음 모두 충족되는 순위의 역수를 평균낸다.
- `source_precision`: 상위 결과 중 기대 source에서 온 chunk 비율이다. 잡 source가 얼마나 섞이는지 보는 보조 지표다.

`source_precision`은 관련 chunk 라벨이 아니라 source 라벨만 사용하므로, 일반적인 `Precision@K`보다 느슨하다.
정밀한 `Precision@K`가 필요하면 평가셋에 각 질문별 relevant chunk id 또는 relevant source+term 조합을 추가해야 한다.

## 현재 해석

production 평가에서 `Recall@K`가 높고 `MRR`이 낮으면 정답이 검색 결과 안에는 있지만 앞쪽에 충분히 안정적으로 나오지 않는다는 뜻이다.
`source_precision`이 낮으면 질문과 무관한 공식문서 source가 상위 결과에 많이 섞인다는 뜻이다.

따라서 retrieval 개선은 다음 순서로 본다.

1. 명시적 source hint가 있는 질문에서 해당 source를 우선하도록 조정한다.
2. pgvector에서 더 넓게 가져온 뒤 local rerank로 최종 순위를 정한다.
3. 청크 분할이 source/조항 경계를 흐리는 케이스를 보정한다.
