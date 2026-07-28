# Agent + RAG 평가셋 검토

> 상태: **보강 평가셋 (`2026-07-28-draft-3`)**
>
> Official RAG와 Policy RAG 변경 전후에는 **같은 Test 질문과 판정 조건**을 사용한다.
> 실행 코드와 데이터 상태는 결과마다 fingerprint로 기록한다.

## 무엇을 확인하나

- **답변 품질**: 필요한 조건을 포함하고 근거에 없는 사실은 만들지 않는가
- **도구 선택**: Policy RAG와 Official RAG를 질문 목적에 맞게 호출하는가
- **근거 경계**: 내 증권의 사실과 공식 자료의 일반 기준을 섞지 않는가
- **안전한 답변**: 근거가 부족할 때 단정하거나 가입·해지를 지시하지 않는가
- **성능**: 전체 응답 시간, 검색 시간, Agent 모델 요청·토큰을 구분해 기록하는가

자동 규칙은 동치 표기(`20만원`/`20만 원`)를 정규화하고, 도구 근거에 없는
기간·비율을 별도로 잡는다. LLM Judge를 사용할 때는 최종 답변만 주지 않고
**실제 도구 결과와 작성자가 확인한 기준 사실**을 함께 전달한다. 실행 오류나
후속 턴 미실행도 실패 결과에 포함해 평가 분모에서 빠지지 않게 한다.

## 구성

| 세트 | 케이스 | 턴 | 용도 |
| --- | ---: | ---: | --- |
| Practice | **24** | **24** | 기존 핵심 시나리오를 반복하며 구현을 조정 |
| Test | **8** | **11** | 새로운 조합·문서 경계·멀티턴 질문으로 최종 비교 |
| 합계 | **32** | **35** | 모든 턴은 실제 `/qa/stream`과 Agent 도구 실행을 거침 |

`test` 결과를 보고 프롬프트나 검색 규칙을 맞추면 더 이상 독립 검증셋이 아니다.
구현을 조정할 때는 `practice`만 사용하고, 단계별 변경을 마친 뒤 `test`를 실행한다.

`draft-3`에서는 증권 발췌문이 부족할 때 별도 Agent 도구 호출에 기대지 않고
`retrieve_policy_terms` 결과에 공식 약관 링크를 함께 반환하도록 Practice의
fallback 기대 동작을 갱신했다. Test 질문과 판정 조건은 `draft-2`와 같다.

## 케이스 목록

### Policy RAG

| ID | 질문 의도 | 핵심 확인 |
| --- | --- | --- |
| `policy_cancer_waiting_period` | 암 보장개시일 | Policy만 호출, 90일 |
| `policy_cancer_reduction` | 진단비 감액 조건 | 1년 이내 50% |
| `policy_medical_deductible` | 실손 자기부담금 | 급여 20%, 비급여 30% |
| `policy_renewal_condition` | 실손 갱신 조건 | 1년 갱신 |
| `policy_auto_deductible` | 자기차량손해 자기부담금 | 20%, 최소·최대 금액 |
| `policy_annual_premium` | 연납과 월납 구분 | 연 720,000원을 월납 합계와 혼동하지 않음 |
| `policy_flight_delay` | 항공기 지연 보장 | 4시간과 보상 비용 |
| `policy_lost_cash_exclusion` | 휴대품손해 제외 | 현금은 보상하지 않음 |
| `policy_fire_damage_boundary` | 본인 집과 이웃집 피해 | 화재손해와 배상책임 구분 |
| `policy_unknown_renewal_rate` | 증권에 없는 미래 인상률 | 임의 비율을 만들지 않음 |

### Official RAG

| ID | 질문 의도 | 핵심 확인 |
| --- | --- | --- |
| `official_cooling_off` | 청약철회 | Official만 호출, 기간과 예외 |
| `official_disclosure_violation` | 계약 전 알릴 의무 | 위반 시 계약 영향 |
| `official_late_premium` | 보험료 연체 | 독촉 기간과 계약 효력 |
| `official_dispute_mediation` | 분쟁 조정 | 금융감독원 조정과 자료 열람 |
| `official_insurance_age` | 보험나이 | 6개월 반올림과 계약해당일 |
| `official_subrogation` | 보험자대위 | 뜻과 가족·임차인 예외 |
| `official_suitability` | 적합성 원칙 | 소비자 정보 확인과 권유 제한 |
| `official_unrelated_question` | 보험 외 질문 | 두 RAG를 모두 호출하지 않음 |

### Policy + Official

| ID | 질문 의도 | 필요한 도구 |
| --- | --- | --- |
| `mixed_waiting_period_meaning` | 내 증권의 90일 조건과 일반적인 면책 개념 | Policy + Official |
| `mixed_indemnity_duplicates` | 내 실손 계약과 일반적인 비례보상 | 보장 중복 조회 + Official |
| `mixed_auto_deductible` | 내 자기부담금과 일반적인 사고 처리 안내 | Policy + Official |
| `mixed_policy_exclusion` | 증권의 면책 안내와 공식 일반 기준 | Policy + Official |
| `mixed_policy_terms_fallback` | 증권에 없는 모든 면책 사유 질문 | Policy + 원문 확인 경로 |
| `mixed_cancel_indemnity` | 실손 중복 계약 해지 질문 | 보장 중복 조회 + Official |

### Test 세트

| ID | 확인 범위 |
| --- | --- |
| `test_policy_cancer_start_comparison` | 한 증권 안에서 암·유사암 시작일 구분 |
| `test_policy_cross_contract_waiting_period` | 첫 번째 증권의 90일 조건을 두 번째 증권에 섞지 않음 |
| `test_policy_travel_loss_boundary` | 도난·파손과 분실·현금의 보상 경계 |
| `test_official_sales_duties_combined` | 적합성 원칙과 설명의무를 함께 검색 |
| `test_official_personal_dispute_result` | 공식 절차와 개인 사건 결과 예측을 구분 |
| `test_multiturn_auto_policy_to_official` | 증권 자기부담금에서 공식 자차 기준으로 전환 |
| `test_multiturn_cross_policy_followup` | 후속 질문에서도 서로 다른 증권 조건을 구분 |
| `test_multiturn_policy_to_official_exclusion` | 증권 면책 문구에서 공식 알릴 의무 기준으로 전환 |

## 확정 전에 볼 부분

- 질문이 실제 사용자가 물을 법한 표현인지
- 기대한 도구 조합이 현재 제품의 책임 경계와 맞는지
- 반드시 포함할 키워드가 너무 엄격하거나 느슨하지 않은지
- 빠진 보험 종류·공식 제도·근거 부족 상황이 있는지
- 같은 사실을 표현만 바꾼 중복 케이스가 과하지 않은지

현재 Policy 평가는 여전히 **4개 샘플 증권**, Official 평가는 저장소의 공식 참조 자료에
기반한다. Test 세트는 기존 질문을 그대로 반복하지 않지만 같은 문서 코퍼스를 사용하므로,
실제 OCR 오류·새로운 보험 종류·운영 문서 분포까지 대표한다고 단정할 수는 없다. 초안을
직접 검토해 빠진 사례를 보강한 뒤 평가셋 버전을 고정한다.
