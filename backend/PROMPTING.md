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
| 상담 agent 지시문 | 파일 유지 | 제품 포지션, 금지 문구, 근거 등급·되묻기 규칙이 길고 중요해 사람이 읽고 고쳐야 함. `qa/instructions.md` |

## 파일로 분리할 때의 규칙

프롬프트 파일을 만들 때는 기본적으로 사용하는 모듈 가까이에 둔다.
`app/modules/*`의 기능 프롬프트는 해당 모듈 옆에, `app/rag/*`의 런타임 프롬프트는 해당 RAG 하위 디렉터리 옆에 둔다.
예를 들어 공식자료 RAG 응답 prompt는 `backend/app/rag/official/rag_answer_prompt.md`에 둔다.

기본 위치 예시는 다음과 같다.

```text
backend/app/modules/policy/...
backend/app/modules/portfolio/...
backend/app/modules/consultation/...
backend/app/modules/counsel/...
backend/app/rag/official/...
backend/app/rag/policy/...
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
| 상담 turn planner | 범위 판단 정확도, 지시어 해소 정확도, 담보명 추출 정확도, 되묻기 선택 적절성 |
| 상담 답변 경로 | 결정적 즉답과 agent 승격의 분기 정확도, 확정 단정 방지, 케이스별 통과율(반복 실행 기준) |

RAG 평가는 retrieval과 generation을 분리해서 본다.
Retrieval 평가는 질문에 맞는 근거를 찾아오는지 측정하고, generation 평가는 이미 주어진 고정 근거만으로 답변 계약을 지키는지 측정한다.
따라서 generation 평가셋에는 검색 랭킹을 기대값으로 넣지 않고, `required_evidence_ids`, `allowed_evidence_ids`, `forbidden_evidence_ids`, `must_include_groups`, `must_not_include`처럼 답변이 어떤 근거를 사용해야 하고 어떤 근거를 쓰면 안 되는지를 명시한다.
특히 업로드 증권(policy) RAG generation 평가는 실제 사용자의 증권 원문 조각을 다루므로, 평가 fixture에는 개인정보 원문을 넣지 않고 `[전화번호]`, `[주민등록번호]`, `[이메일]`, `[계좌번호]` 같은 마스킹 토큰만 둔다.
다중 증권, 같은 담보명 충돌, OCR 노이즈, 프롬프트 인젝션, 긴 distractor, 근거 부족 fallback처럼 generation 단계에서 흔히 깨지는 edge case를 별도 케이스로 유지한다.

Policy RAG generation 평가는 practice와 test를 분리한다.
practice는 실패 원인을 분석하고 프롬프트·후처리를 반복 개선하는 데 사용하며,
단일 fixture인 `backend/evals/rag/policy/generation_dataset.json`에 둔다.
정답 근거가 첫 위치에 몰리지 않도록 3개 이상의 근거, 다중 근거 정답,
관련 있어 보이는 근거 부족 사례, 실제 샘플 증권에서 비식별화한 edge case를 충분히 포함한다.
test는 `backend/evals/rag/policy/generation_test_dataset.json`에 따로 두고
practice 개선을 끝낸 뒤 별도 fixture로 한 번만 실행한다.
test 결과를 본 뒤 같은 test에 맞춰 수정하지 않으며,
추가 개선이 필요하면 해당 실패 유형은 다음 practice에 반영하고 새로운 test로 다시 검증한다.
질문을 읽지 않고 첫 근거만 고르는 baseline도 함께 측정해 평가셋 자체가 지나치게 쉽지 않은지 확인한다.

Policy RAG generation은 공용 상담 생성기가 아니라 `backend/app/rag/policy/generation.py`의 독립 생성기를 사용한다. 평가 러너도 이 생성기를 직접 호출해 검색 품질이나 공용 상담 후처리 변경 없이 policy 답변 계약만 측정한다.

## 평가 실행

평가 러너는 `backend/evals` 아래에 있다. module path 기준 실행 명령은 다음과 같다.

```bash
cd backend
uv run python -m evals.rag.official.retrieval
uv run python -m evals.rag.official.generation --show-passing
uv run python -m evals.rag.policy.retrieval
uv run python -m evals.rag.policy.generation --set practice --show-passing
uv run python -m evals.rag.policy.generation --set test
```

`official` 평가는 공식문서 retrieval/generation 품질을 다루고, `policy` 평가는 업로드 세션 RAG의 retrieval/generation 품질을 다룬다. 운영 API correctness는 `tests/`가 담당하고, `evals`는 품질 회귀를 보는 별도 계층이다.

## 현재 결정

- 기본정보 보완 추출과 보험분류 fallback은 **코드 안에 둔다**.
- 두 fallback은 제거하지 않는다. deterministic rule이 먼저 잡으면 호출하지 않고, 규칙이 실패할 때만 fallback으로 둔다.
- 보험사 추출은 특정 보험사 alias, 도메인, 브랜드 전용 데이터로 보정하지 않는다. false positive가 더 위험하므로 LLM fallback과 grounding에 맡긴다.
- 프롬프트 구조화는 실제 API 비교로 검증한다. 기본정보 보완 추출처럼 구조화가 timeout이나 품질 저하를 만들면 적용하지 않는다.
- 포트폴리오 총평은 자유 문장 생성이 아니라 Pydantic `Literal` 스키마에 정의된 중립 문장을 선택하는 방식으로 생성한다. LLM 입력에는 보험료 권장 범위·높고 낮음 같은 비교 판단을 전달하지 않고, 선택된 문장은 현재 요약 사실에 맞는지 서버가 다시 검증한다. 보험료·보장·다음 확인 takeaway는 결정적 계산 결과를 사용한다.
- 상담은 `POST /qa/stream` 하나를 외부 API로 본다. `stream`은 전송 방식이고, 답변 도메인 모델은 하나로 본다. (구 `POST /counsel/stream`은 비교용으로 잠시 남겨두었고, 확인이 끝나면 제거한다.)
- 상담 turn은 도구를 가진 agent 하나를 호출한다. 범위 판단·질문 재작성·사실 조회를 앞단 planner로 쪼개지 않는다. 재작성은 agent가 도구를 부를 때 넘기는 인자 자체로 처리하고, 범위 판단은 답변 문장에서 드러난다. 앞단에서 해석을 확정하면 도구 결과를 보고 되돌릴 수 없어, 측정한 실패의 상당수가 그 단계에서 나왔기 때문이다.
- 보험 사실(금액, 개수, 합계, 중복, 청구 채널)은 결정적 코드가 계산하고, agent는 그 값을 그대로 인용한다. 합계가 필요하면 agent가 암산하지 않고 합계 도구를 부른다. LLM이 사실을 만들지 않는다.
- agent 출력에는 슬롯·구조화 출력 같은 사후 강제 장치를 두지 않는다. 두 번의 시도(슬롯 참조, 구조화 출력)가 막으려던 오귀속은 실제 측정에서 드물었고, 장치 자체가 답변을 더 망가뜨렸다. 대신 `evals/qa/rules.py`가 답변의 금액이 증권 데이터나 그 턴의 도구 결과에 실제로 있는지 사후에 검사한다.
- 사용자가 입력한 질문과 대화 이력은 외부 모델 호출 전에 주민등록번호·전화번호·이메일을 마스킹한다. 모델에 보내는 것은 트레이싱 같은 부가 경로로도 함께 나갈 수 있다고 보고, 마스킹은 라우터 한 곳에서 적용한다.
- agent SDK의 트레이싱은 대화 내용을 외부 저장소로 내보내므로 끈다. 키는 프로세스 환경변수로 export하지 않고 SDK 진입점으로 전달한다.
- 명백한 도메인 밖 질문은 보험 상담 답변으로 흘려보내지 않는다. 복합 질문에 외부 도메인이 섞이면 보험 부분만 남기고, 뺀 내용은 사용자에게 알린다.
