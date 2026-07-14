# LLM 프롬프트 작성 가이드

Coverly의 LLM 프롬프트는 사용자의 보험 정보를 근거 기반으로 구조화하거나 설명하기 위한 런타임 계약이다. 프롬프트는 문장 품질보다 먼저 **정확성, grounding, 안전성, 검증 가능성**을 지켜야 한다.

## 기본 원칙

- **결정적 처리 우선**: regex, parser, taxonomy, rules, retrieval, template로 안정적으로 처리할 수 있으면 LLM에 보내지 않는다.
- **LLM은 좁은 역할만 맡긴다**: 한 프롬프트가 추출, 판단, 설명, 추천을 모두 하게 만들지 않는다.
- **근거 없으면 거절**: 원문, retrieval hit, evidence catalog에 없는 보장 판단·지급 판단·가입 권유를 만들지 않는다.
- **빈 값이 틀린 값보다 낫다**: 기본정보, 금액, 사람 이름, 증권번호처럼 사용자 화면의 사실값은 확실하지 않으면 `null`, `미분류`, `확인 불가`를 선택한다.
- **후처리와 한 세트로 설계**: 프롬프트 지시만 믿지 않고 schema, enum, citation 검증, grounding, 안전 문구 필터로 강제한다.
- **실데이터로 평가**: `sample-insurance-input` 같은 실제 PDF와 골든 기대값으로 before/after를 비교한다.

## 권장 프롬프트 구조

짧은 프롬프트도 가능한 한 사람이 읽기 쉬운 구조를 유지한다. 다만 구조화를 위해 불필요하게 길게 만들면 latency와 timeout이 늘 수 있으므로, **구조적이되 짧게** 쓴다.

```text
# 역할
너는 ...

# 목표
...

# 입력
- ...

# 작업 순서
1. ...
2. ...
3. ...

# 해야 할 것
- ...

# 하지 말아야 할 것
- ...

# 불확실할 때
- ...

# 출력 규칙
- ...
```

모든 섹션을 항상 넣을 필요는 없다. 특히 schema가 강한 structured output 프롬프트는 `역할`, `작업 순서`, `해야 할 것`, `하지 말아야 할 것` 정도만으로 충분할 수 있다.

## 코드에 둘지 파일로 뺄지

프롬프트 위치는 길이와 변경 주체에 따라 결정한다.

| 기준 | 코드 안 문자열 유지 | 별도 `.md`/`.txt` 파일 |
|---|---|---|
| 길이 | 짧음 | 길거나 예시가 많음 |
| schema 결합도 | Pydantic schema, enum과 강하게 붙음 | 자연어 생성 정책이 중심 |
| 변경 주체 | 개발자가 코드와 함께 수정 | 제품/UX/도메인 리뷰가 필요 |
| 변수 삽입 | 단순 문자열 조합 | evidence, history, examples 등 복잡 |
| 테스트 | 코드 옆 단위 테스트가 핵심 | placeholder/필수 섹션 테스트 필요 |

현재 추천 위치는 아래와 같다.

| 프롬프트 | 추천 위치 | 이유 |
|---|---|---|
| 기본정보 보완 추출 | 코드 유지 | 짧고 schema와 강하게 결합. 실제 비교에서 과한 구조화가 timeout을 유발할 수 있었음 |
| 보험분류 fallback | 코드 유지 | enum 분류 프롬프트이고 짧음. 구조화하되 코드 옆 테스트로 고정 |
| 담보 표 정규화 | 파일 후보 | 표 해석 규칙, negative examples, degrade 정책이 길어질 가능성이 큼 |
| 담보 일반 해설 | 파일 후보 | 사용자 설명 톤, 공식자료 근거 제한, 설명 불가 정책을 사람이 읽어야 함 |
| 상담사형 분석 생성 | 파일 권장 | 제품 포지션, 금지 문구, evidence 사용 규칙이 길고 중요 |
| 공식자료 RAG 응답 | 파일 권장 | citation discipline, no-evidence 정책, 약관 왜곡 방지 규칙이 중요 |
| 일반 상담형 QA | 파일 권장 | 대화 이력, confirmed facts, guidance, limitations 역할 분리가 필요 |
| 일반 상담형 스트리밍 QA | 파일 권장 | non-stream과 품질 계약을 맞추고 `CLARIFY`, citation 후처리 규칙을 명확히 해야 함 |

## 파일로 분리할 때의 규칙

프롬프트 파일을 만들 때는 기본적으로 `backend/app/services/prompts/` 아래에 둔다.
다만 RAG처럼 prompt가 특정 pipeline, evaluation dataset, 후처리 contract와 강하게 결합된 경우에는 사용하는 코드 가까이에 둔다.
예를 들어 공식자료 RAG 응답 prompt는 `backend/app/services/rag/official/rag_answer_prompt.md`에 둔다.

기본 위치 예시는 다음과 같다.

```text
backend/app/services/prompts/
  coverage_normalization.md
  coverage_explanation.md
  portfolio_analysis.md
  rag_answer.md
  portfolio_qa.md
  portfolio_qa_stream.md
```

파일 분리 시에는 반드시 다음을 함께 둔다.

- 프롬프트 로더: UTF-8로 읽고 캐시한다.
- placeholder 검증: `{{question}}`, `{{evidence_catalog}}` 같은 필수 변수가 누락되면 테스트에서 실패한다.
- 필수 섹션 테스트: `# 역할`, `# 하지 말아야 할 것`, `# 출력 규칙` 등 해당 프롬프트의 핵심 섹션을 검증한다.
- golden/eval 테스트: 샘플 입력에서 before/after 출력 품질을 비교한다.

## 작성 체크리스트

프롬프트를 새로 만들거나 바꿀 때 아래를 확인한다.

- 이 LLM 호출 전에 deterministic route로 끝낼 수 있는 케이스를 먼저 분기했는가?
- 입력 context가 너무 많거나, 반대로 필요한 근거가 빠지지 않았는가?
- 출력 schema와 프롬프트의 출력 규칙이 같은 계약을 말하는가?
- `해야 할 것`과 `하지 말아야 할 것`이 분리되어 있는가?
- 순서가 중요한 작업은 numbered steps로 적었는가?
- 근거 부족 시 행동이 명시되어 있는가?
- 특정 보험사·상품 전용 휴리스틱을 넣지 않았는가?
- 개인정보가 LLM 입력 전에 마스킹되는가?
- 후처리에서 citation id, amount grounding, enum, unsafe text를 검증하는가?
- 실제 샘플로 before/after를 비교했는가?

## 평가 기준

프롬프트 변경은 “더 좋아 보인다”가 아니라 지표로 판단한다.

| 유형 | 주요 지표 |
|---|---|
| 정보 추출 | 필드별 precision/recall, 잘못 채택된 값 수, grounding 통과율, LLM 호출률 |
| 분류 | 정확도, enum별 혼동, `미분류` 적절성, 규칙 hit율 |
| 표 정규화 | 담보 row recall, 금액 grounding 통과율, 원문 없는 보장내용 제거율, degrade 비율 |
| RAG 답변 | citation 정확도, no-evidence 판정, retrieval hit 적합도, 약관 왜곡 수 |
| Policy RAG 생성 | 고정 evidence 기반 답변 계약, citation precision, 금지 근거 미사용, PII 마스킹 유지, 판매·지급 단정 방지 |
| 상담/분석 생성 | evidence 일치율, 판매·공포 문구 발생률, 중복 insight, next action 품질 |
| Q&A planner | planner 호출률, 지시어 해소 정확도, 복합 질문 분리, 도메인 밖 질문 제한, planner 장애 시 fallback 안정성 |
| 스트리밍 | non-stream parity, citation 후처리 성공률, `CLARIFY` 처리, fallback 안정성, 질문 추천 형식 |

RAG 평가는 retrieval과 generation을 분리해서 본다.
Retrieval 평가는 질문에 맞는 근거를 찾아오는지 측정하고, generation 평가는 이미 주어진 고정 근거만으로 답변 계약을 지키는지 측정한다.
따라서 generation 평가셋에는 검색 랭킹을 기대값으로 넣지 않고, `required_evidence_ids`, `allowed_evidence_ids`, `forbidden_evidence_ids`, `must_include_groups`, `must_not_include`처럼 답변이 어떤 근거를 사용해야 하고 어떤 근거를 쓰면 안 되는지를 명시한다.
특히 업로드 증권(policy) RAG generation 평가는 실제 사용자의 증권 원문 조각을 다루므로, 평가 fixture에는 개인정보 원문을 넣지 않고 `[전화번호]`, `[주민등록번호]`, `[이메일]`, `[계좌번호]` 같은 마스킹 토큰만 둔다.
다중 증권, 같은 담보명 충돌, OCR 노이즈, 프롬프트 인젝션, 긴 distractor, 근거 부족 fallback처럼 generation 단계에서 흔히 깨지는 edge case를 별도 케이스로 유지한다.

Policy RAG generation 평가는 practice와 test를 분리한다. practice는 실패 원인을 분석하고 프롬프트·후처리를 반복 개선하는 데 사용하며, 단일 fixture인 `app/services/rag/policy/evaluation/generation_dataset.json`에 둔다. 정답 근거가 첫 위치에 몰리지 않도록 3개 이상의 근거, 다중 근거 정답, 관련 있어 보이는 근거 부족 사례, 실제 샘플 증권에서 비식별화한 edge case를 충분히 포함한다. test는 `app/services/rag/policy/evaluation/generation_test_dataset.json`에 따로 두고 practice 개선을 끝낸 뒤 별도 fixture로 한 번만 실행한다. test 결과를 본 뒤 같은 test에 맞춰 수정하지 않으며, 추가 개선이 필요하면 해당 실패 유형은 다음 practice에 반영하고 새로운 test로 다시 검증한다. 질문을 읽지 않고 첫 근거만 고르는 baseline도 함께 측정해 평가셋 자체가 지나치게 쉽지 않은지 확인한다.

Policy RAG generation은 공용 상담 생성기가 아니라 `app/services/rag/policy/generation.py`의 독립 생성기를 사용한다. 평가 러너도 이 생성기를 직접 호출해 검색 품질이나 공용 QA 후처리 변경 없이 policy 답변 계약만 측정한다.

## 현재 결정

- 기본정보 보완 추출과 보험분류 fallback은 **코드 안에 둔다**.
- 두 fallback은 제거하지 않는다. deterministic rule이 먼저 잡으면 호출하지 않고, 규칙이 실패할 때만 fallback으로 둔다.
- 보험사 추출은 특정 보험사 alias, 도메인, 브랜드 전용 데이터로 보정하지 않는다. false positive가 더 위험하므로 LLM fallback과 grounding에 맡긴다.
- 프롬프트 구조화는 실제 API 비교로 검증한다. 기본정보 보완 추출처럼 구조화가 timeout이나 품질 저하를 만들면 적용하지 않는다.
- Q&A는 외부 API 기준으로 `POST /qa/stream` 하나만 유지한다. `stream`은 전송 방식이고, 답변 도메인 모델은 하나로 본다.
- 단순한 보험 사실 질문은 planner를 거치지 않고 결정적 fast path를 우선한다. planner는 지시어 해소, 복합 질문 분리, 명백한 도메인 밖 질문, 인사처럼 대화 turn을 정리해야 할 때만 호출한다.
- planner 입력에는 최근 12개 대화만 넣고, 주민등록번호 형태뿐 아니라 전화번호와 이메일도 외부 모델 호출 전에 마스킹한다.
- planner가 실패해도 명백한 도메인 밖 질문은 보험 상담 답변으로 흘려보내지 않는다. 복합 질문에 외부 도메인이 섞이면 가능한 범위에서 보험 부분과 외부 도메인 부분을 나누고, 외부 도메인 부분은 정중하게 제한한다.
- 후속 질문 추천은 사용자가 그대로 누를 수 있는 질문 원문만 사용한다. `~해 보세요`, `~확인해 주세요` 같은 행동 제안 문장은 추천 질문에 넣지 않고, 최대 3개만 반환한다.
- Q&A 응답 속도는 실제 시간 임계값보다 호출 경로로 먼저 관리한다. 단순 가입금액·보유 목록·청구 채널 질문은 planner completer, policy RAG, 상담 LLM을 호출하지 않아야 한다.
- planner만으로 끝나는 인사·도메인 밖 질문·되묻기 turn은 포트폴리오 facts/catalog 계산을 만들지 않는다.
