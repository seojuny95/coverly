# 상담 Agent 평가

현재 상담 Agent의 전체 자동 평가 기준선과 사람 검수 결과를 기록한다.

- [자동 평가와 사람 검수 판정이 포함된 결과](results.json)

## 실행 조건

| 항목             | 조건                                         |
| ---------------- | -------------------------------------------- |
| 평가셋           | 70개 대화·89턴                               |
| 실행 횟수        | 각 케이스 1회                                |
| Agent·Judge 모델 | `gpt-4o-mini`                                |
| 실행 경로        | fixture 증권을 사용한 실제 `POST /qa/stream` |
| 자동 평가        | 예상 키워드·결정적 규칙·LLM-as-a-Judge       |

한 번의 실행 결과이므로 모델 변동성까지 대표하지는 않는다. 반복 실행 기준선은 후속 평가에서 별도로 만든다.

## 자동 평가 결과

| 전체 | 통과 | 실패 | 통과율 |
| ---: | ---: | ---: | -----: |
|   89 |   61 |   28 |  68.5% |

## 사람 검수 반영 결과

사람 검수는 자동 평가가 실패로 분류한 28턴을 대상으로 진행했다. `human_verdict`가 있는 턴은 사람 판정을 적용하고, `human_verdict: null`인 자동 통과 턴은 기존 통과 판정을 유지한다.

| 구분                   |     턴 |
| ---------------------- | -----: |
| 전체 평가셋            |     89 |
| 자동 통과 유지         |     61 |
| 자동 실패 중 사람 통과 |     21 |
| 자동 실패 중 사람 실패 |      7 |
| 미검수 자동 실패       |      0 |
| **최종 통과**          | **82** |
| **최종 실패**          |  **7** |

자동 평가가 실패로 분류한 28턴 중 21턴은 사람이 통과로 판정을 바꿨고 7턴은 실패 판정에 동의했다. 이를 자동 통과 61턴과 합치면 검수 반영 결과는 **82/89턴(92.1%) 통과**, **7/89턴(7.9%) 실패**다.

### 사람이 통과로 판정한 자동 실패 21턴

- `fact_policy_count#1`
- `fact_policy_list#1`
- `fact_coverage_exact#1`
- `fact_overlap_fixed_amount#1`
- `fact_overlap_indemnity#1`
- `grounding_missing_coverage#1`
- `grounding_general_knowledge#1`
- `scope_mixed#1`
- `advice_portfolio_review#1`
- `clarify_recovery#1`
- `multiturn_long_then_switch#2`
- `messy_typo_heavy#1`
- `messy_colloquial#1`
- `messy_run_on#1`
- `messy_multiple_questions#1`
- `messy_rude_terse#1`
- `messy_emotional_complaint#1`
- `adversarial_false_premise_amount#2`
- `adversarial_asks_for_guarantee#1`
- `special_policy_auto_confirmed#1`
- `vague_no_context_at_all#1`

### 사람이 실패로 판정한 자동 실패 7턴

- `advice_cancel_request#1`
- `multiturn_correction#2`
- `situational_illness#1`
- `situational_car_accident#1`
- `situational_car_accident#2`
- `special_policy_driver_lawyer_fee#1`
- `disclosure_precedence_over_policy_terms#1`

## 해석할 때 주의할 점

- 사람은 자동 실패 28턴을 재판정했고, 자동 통과 61턴은 기존 판정을 유지했다.
- 자동 실패의 75.0%인 21턴이 사람 검수에서 통과로 바뀌어, 현재 자동 평가가 올바른 답변을 과도하게 실패 처리하는 문제가 크다.
- 82/89는 사람 검수로 자동 실패를 조정한 결과다. 자동 통과 사례에서 평가기가 놓친 실패가 없는지를 별도로 분석하는 지표는 아니다.
- 자동 평가 기준선 61/89와 사람 검수 반영 기준선 82/89를 함께 기록한다.

## 다음 평가에서 보완할 점

- 올바른 되묻기, 의미가 같은 표현, 근거가 드러난 목록형 답변을 자동 평가가 실패로 잡지 않도록 rubric과 키워드 조건을 보완한다.
- 자동 통과 사례를 표본 검수해 자동 평가의 누락 유형을 별도로 분석한다.
- 단일 실행의 우연을 줄이기 위해 주요 실패군부터 반복 실행한다.
