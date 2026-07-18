# Policy RAG 평가 기록

업로드한 보험증권을 세션 범위 안에서 검색하는 policy RAG의 평가 기록이다.
평가 데이터셋에는 주민등록번호, 전화번호, 이메일 같은 원문 개인정보를 넣지 않는다.

## Retrieval

평가셋은 실제 샘플 PDF 4개를 파싱해 만든 세션별 chunk를 대상으로 한다. 기본정보,
담보명·가입금액, 후기 페이지 유의사항, 구어체/붙여쓰기 질문, 여러 증권 중 목표
계약을 골라야 하는 hard-negative 케이스를 포함한다.

| 단계 | 케이스 | recall@5 | precision@5 | MRR | session precision | 개선 내용 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| baseline | 122 | 0.656 | 0.198 | 0.355 | 0.910 | vector score만 사용해 같은 세션 안 관련 chunk 랭킹이 약했다. |
| hybrid rerank | 122 | 0.918 | 0.313 | 0.667 | 0.928 | 후보를 넓히고 BM25/RRF로 재정렬했다. |
| query expansion | 122 | 0.934 | 0.321 | 0.671 | 0.933 | 보험 문서에서 자주 달라지는 표현과 금액 단위 표기를 보강했다. |

현재 남은 실패는 대부분 여러 증권이 함께 들어왔을 때 질문 표현만으로 목표 계약을
정확히 고르는 케이스다. 예를 들어 “4만원대 어린이보험”처럼 금액 범위가 암시된
질문은 검색기만으로 안정적으로 해결하기 어렵고, 상위 QA 단계의 후보 비교나
structured summary 결합이 필요하다.

## Generation

평가셋은 retrieval이 이미 넘긴 증권 근거를 고정해 두고, 답변 생성 단계만 본다.
개인정보는 원문 값 대신 `[이름]`, `[전화번호]`, `[계좌번호]`, `[주소]`, `[이메일]`처럼
마스킹한 값만 사용한다.

| 구분 | 케이스 | 주요 구성 |
| --- | ---: | --- |
| practice | 94 | 기본 계약 정보, 보장 조건, 다중 근거, 실손/자동차/운전자 경계, 개인정보 마스킹, prompt injection, 근거 부족 fallback |
| test | 20 | practice와 ID가 겹치지 않는 독립 케이스. hard-negative, 다중 근거, OCR spacing, prompt injection, 부분 답변을 포함 |

현재 CI/로컬에서 항상 돌릴 수 있도록 `--offline-lexical` 모드를 추가했다. 이 모드는
LLM 품질을 대신하지 않는다. API 키 없이도 citation, fallback, forbidden text 같은
generation contract가 깨지는지 확인하기 위한 결정적 기준선이다.

| 단계 | 평가 방식 | practice pass_rate | test pass_rate | 주요 결과 |
| --- | --- | ---: | ---: | --- |
| baseline | offline lexical | 0.457 | 0.350 | 정확한 갱신 인상률, 청구서류 전체, 수익자처럼 증권에 없는 세부값을 일부 답변 경로로 통과시켰다. |
| missing-specific guard | offline lexical | 0.457 | 0.500 | 갱신 후 정확한 금액/인상률, 청구서류 전체, 수익자 미기재 질문은 LLM 호출 전 fallback 하도록 막았다. prompt에도 같은 경계를 명시했다. |
| missing-specific guard | live LLM | 0.851 | 0.850 | main worktree의 backend `.env`를 로드해 실측했다. 남은 실패는 주로 불필요한 근거까지 함께 고르는 과선택과 부분 답변 fallback이다. |

offline 실패의 대부분은 lexical completer의 한계다. 예를 들어 조사·띄어쓰기,
동의어, “둘 다” 같은 복합 의도를 충분히 처리하지 못한다. live LLM 기준 남은 실패는
프롬프트와 후처리에서 선택 evidence를 더 좁히는 방향으로 봐야 한다.

## 결정

- 평가 정답 문자열을 runtime 코드에 직접 넣지 않는다.
- `4만원대 → 42,615원` 같은 샘플 전용 매핑은 넣지 않는다.
- 허용한 query expansion은 일반 표현 차이만 다룬다.
  - `차값` ↔ `차량가액`
  - `심장질환` ↔ `심질환`
  - `월 보험료` ↔ `1회 보험료`
  - `2억원` ↔ `20,000만원`
- retrieval은 후보 검색과 랭킹을 담당한다. 범위 밖 질문 거절이나 여러 계약 비교
  판단은 generation/e2e 또는 structured summary 결합에서 별도로 평가한다.

## RAG E2E

Policy RAG E2E는 업로드 증권 세션 corpus를 검색한 뒤, 검색 결과를 그대로 policy generation에 넣어 최종 답변 계약을 확인한다.
QA router/planner는 거치지 않는다.

### 평가셋 구성

- 총 171개 케이스.
- 기존 retrieval 평가셋 전체 122개를 retrieval→generation으로 다시 실행한다.
- 별도 `no_data`/hard-negative 49개를 추가했다.
- 운전자보험, 어린이보험, 자동차보험, 제3보험 기본정보, 담보 금액, 후기 페이지 유의사항, 다중 세션 hard-negative, 실손의료보험 혼동, 개인 상황 판단 불가, 실제 사고/청구 판단 불가, 수익자/환급금/해지/대출/세금 같은 증권 밖 질문을 포함한다.
- 평가셋에는 실제 개인정보를 넣지 않고 `sample-*` 세션 ID와 일반 질문만 사용한다.
- 기본 completer는 검색된 evidence를 그대로 선택하는 deterministic extractive 방식이다.

### 개선 기록

| 단계 | 결과 | 개선 내용 |
| --- | ---: | --- |
| RAG E2E v1 baseline | 19/19, pass_rate 1.000 | 대표 케이스만 골라 연결 smoke test로 시작했다. 부족한 지점을 충분히 드러내지 못했다. |
| RAG E2E broad baseline | 118/134, pass_rate 0.881 | retrieval 전체 세트와 no_data/hard-negative를 추가했다. 다중 세션 hard-negative, 실손의료보험 혼동, 수익자/면책/개인 상황 판단 no_data에서 실패가 드러났다. |
| RAG E2E reliable baseline | 123/171, pass_rate 0.719 | no_data/hard-negative를 49개까지 늘렸다. 실손의료보험 혼동, 실제 사고/청구 판단, 수익자/환급금/해지/대출/세금 등 증권 밖 질문에서 answered로 흐르는 문제가 뚜렷해졌다. |
