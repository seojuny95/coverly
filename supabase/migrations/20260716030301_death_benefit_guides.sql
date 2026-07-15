insert into reference.reference_data (key, payload, source, verified_at)
values (
  'death_benefit_guides',
  $json${
  "_meta": {
    "설명": "사망보험금 안내 범위. 공식 적정 기준이 아니라 부양가족, 미성년 자녀, 큰 부채 여부에 따른 점검용 참고 범위다.",
    "갱신일": "2026-07-16"
  },
  "sources": [
    {
      "id": "mk_death_income_multiple_2020",
      "label": "매일경제 · 가장의 적정 사망보험금은 연소득 3~5배",
      "url": "https://www.mk.co.kr/news/economy/9495174",
      "published_at": "2020-08-28",
      "reliability": "private_guidance",
      "caveat": "민간 재무설계 관점의 일반 가이드이며 개인별 적정 보험금의 공식 기준은 아니다."
    },
    {
      "id": "mk_death_income_debt_2019",
      "label": "매일경제 · 종신보험 보장금 수준, 연봉 3배+대출금 적당",
      "url": "https://www.mk.co.kr/news/economy/8884760",
      "published_at": "2019-07-05",
      "reliability": "private_guidance",
      "caveat": "민간 재무설계 관점의 일반 가이드이며 부채와 가족 상황을 함께 보라는 참고 자료다."
    }
  ],
  "guides": [
    {
      "has_dependent_family": false,
      "has_minor_children": false,
      "has_major_debt": false,
      "situation": "부양가족이나 큰 부채가 없는 경우",
      "amount_label": "0원~5천만 원",
      "min_amount": 0,
      "max_amount": 50000000,
      "reason": "사망보험금은 남은 가족의 생활비 공백을 메우는 목적이 크기 때문에, 부양가족이나 큰 부채가 없다면 큰 금액의 필요성은 낮아요. 장례비, 정리비, 부모 지원 정도만 고려하면 돼요.",
      "source_ids": ["mk_death_income_multiple_2020", "mk_death_income_debt_2019"]
    },
    {
      "has_dependent_family": true,
      "has_minor_children": false,
      "has_major_debt": false,
      "situation": "배우자나 가족이 내 소득에 일부 의존하는 경우",
      "amount_label": "5천만~1.5억 원",
      "min_amount": 50000000,
      "max_amount": 150000000,
      "reason": "갑작스러운 소득 공백이 생길 수 있으므로 일정 기간의 생활비가 필요해요. 다만 미성년 자녀나 큰 부채가 없다면 장기간의 고액 보장보다는 1년 안팎의 생활비 수준이 현실적이에요.",
      "source_ids": ["mk_death_income_multiple_2020", "mk_death_income_debt_2019"]
    },
    {
      "has_dependent_family": false,
      "has_minor_children": true,
      "has_major_debt": false,
      "situation": "자녀 양육비와 교육비가 남아 있는 경우",
      "amount_label": "1억~2억 원",
      "min_amount": 100000000,
      "max_amount": 200000000,
      "reason": "미성년 자녀가 있으면 양육비와 교육비가 계속 발생해요. 다만 다른 소득원이 있거나 부채가 크지 않다면, 기본 생활비와 교육비 일부를 보완하는 수준으로 볼 수 있어요.",
      "source_ids": ["mk_death_income_multiple_2020", "mk_death_income_debt_2019"]
    },
    {
      "has_dependent_family": true,
      "has_minor_children": true,
      "has_major_debt": false,
      "situation": "가족 생활비와 자녀 양육비를 함께 책임지는 경우",
      "amount_label": "2억~3억 원",
      "min_amount": 200000000,
      "max_amount": 300000000,
      "reason": "가족이 내 소득에 의존하고 미성년 자녀도 있다면 생활비, 양육비, 교육비 공백이 함께 생겨요. 국내 재무설계 기준에서 자주 언급되는 연소득 3~5배 또는 생활비 3년치 기준을 적용하면 2억~3억 원이 현실적인 기본 범위예요.",
      "source_ids": ["mk_death_income_multiple_2020", "mk_death_income_debt_2019"]
    },
    {
      "has_dependent_family": false,
      "has_minor_children": false,
      "has_major_debt": true,
      "situation": "주담대·전세대출 등 갚아야 할 큰 부채가 있는 경우",
      "amount_label": "5천만~1.5억 원 + 부채 고려",
      "min_amount": 50000000,
      "max_amount": 150000000,
      "reason": "부양가족이 없더라도 대출이 남아 있다면 가족이나 상속인이 정리해야 할 부담이 생길 수 있어요. 기본 정리비용에 부채 일부 또는 전액을 추가로 고려하는 게 좋아요.",
      "source_ids": ["mk_death_income_multiple_2020", "mk_death_income_debt_2019"]
    },
    {
      "has_dependent_family": true,
      "has_minor_children": false,
      "has_major_debt": true,
      "situation": "가족 생활비와 대출 부담이 함께 남는 경우",
      "amount_label": "1.5억~3억 원",
      "min_amount": 150000000,
      "max_amount": 300000000,
      "reason": "내 소득이 사라지면 가족의 생활비와 대출 상환 부담이 동시에 남아요. 그래서 단순 생활비보다 더 높은 보장이 필요할 수 있고, 대출 규모에 따라 3억 원 안팎까지 검토할 수 있어요.",
      "source_ids": ["mk_death_income_multiple_2020", "mk_death_income_debt_2019"]
    },
    {
      "has_dependent_family": false,
      "has_minor_children": true,
      "has_major_debt": true,
      "situation": "자녀 양육비와 대출 부담이 함께 남는 경우",
      "amount_label": "2억~4억 원",
      "min_amount": 200000000,
      "max_amount": 400000000,
      "reason": "자녀가 있으면 양육비·교육비가 계속 들고, 여기에 주담대나 전세대출까지 있으면 남은 가족의 부담이 커져요. 생활비 3년치에 부채를 더하는 방식으로 보면 2억 원 이상이 필요할 수 있어요.",
      "source_ids": ["mk_death_income_multiple_2020", "mk_death_income_debt_2019"]
    },
    {
      "has_dependent_family": true,
      "has_minor_children": true,
      "has_major_debt": true,
      "situation": "가족 생활비, 자녀 양육비, 대출 부담을 모두 책임지는 경우",
      "amount_label": "3억~5억 원",
      "min_amount": 300000000,
      "max_amount": 500000000,
      "reason": "가장의 소득 공백, 자녀 양육비·교육비, 대출 상환 부담이 모두 남는 상황이에요. 이 경우 사망보험금은 단순 장례비가 아니라 가족이 몇 년간 생활을 유지하고 부채를 정리할 수 있는 금액이어야 하므로 3억~5억 원 수준을 검토할 수 있어요.",
      "source_ids": ["mk_death_income_multiple_2020", "mk_death_income_debt_2019"]
    }
  ]
}$json$::jsonb,
  'migration:20260716030301_death_benefit_guides',
  now()
)
on conflict (key) do update set
  payload = excluded.payload,
  source = excluded.source,
  verified_at = excluded.verified_at,
  updated_at = now();
