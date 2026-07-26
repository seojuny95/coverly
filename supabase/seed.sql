-- Local reference data for a brand-new Coverly environment.
-- Apply after supabase/bootstrap.sql.
-- Existing rows are never overwritten.

insert into reference.sources (
  id,
  title,
  publisher,
  url,
  published_at,
  reliability,
  caveat
) values
  (
    'kosis_income_by_age_2025',
    '성별 연령대별 소득',
    'KOSIS 국가통계포털',
    'https://kosis.kr',
    date '2025-01-01',
    'official',
    '연령대 평균 소득은 개인 소득과 다를 수 있어요.'
  ),
  (
    'banksalad_premium_burden_guide_2025',
    '나에게 맞는 보험료 계산법',
    '뱅크샐러드',
    'https://www.banksalad.com/articles/%EB%B3%B4%ED%97%98-%EB%B3%B4%ED%97%98%EB%A6%AC%EB%AA%A8%EB%8D%B8%EB%A7%81-%EB%B3%B4%ED%97%98%EB%A3%8C',
    date '2025-01-01',
    'private_guidance',
    '월 소득의 5%~10% 범위는 민간 가이드이며 적정 보험료의 공식 기준은 아니에요.'
  )
on conflict (id) do nothing;

insert into reference.premium_burden_guides (
  income_source_id,
  guide_source_id,
  age_band_label,
  min_age,
  max_age,
  average_monthly_income,
  suggested_min_ratio,
  suggested_max_ratio,
  effective_at,
  basis
) values
  ('kosis_income_by_age_2025', 'banksalad_premium_burden_guide_2025', '20~29세', 20, 29, 2630000, 0.05, 0.10, date '2025-01-01', '연령대 평균 소득에 민간 가이드 5~10% 적용'),
  ('kosis_income_by_age_2025', 'banksalad_premium_burden_guide_2025', '30~39세', 30, 39, 3860000, 0.05, 0.10, date '2025-01-01', '연령대 평균 소득에 민간 가이드 5~10% 적용'),
  ('kosis_income_by_age_2025', 'banksalad_premium_burden_guide_2025', '40~49세', 40, 49, 4510000, 0.05, 0.10, date '2025-01-01', '연령대 평균 소득에 민간 가이드 5~10% 적용'),
  ('kosis_income_by_age_2025', 'banksalad_premium_burden_guide_2025', '50~59세', 50, 59, 4290000, 0.05, 0.10, date '2025-01-01', '연령대 평균 소득에 민간 가이드 5~10% 적용'),
  ('kosis_income_by_age_2025', 'banksalad_premium_burden_guide_2025', '60세 이상', 60, 120, 2500000, 0.05, 0.10, date '2025-01-01', '연령대 평균 소득에 민간 가이드 5~10% 적용')
on conflict (age_band_label, effective_at) do nothing;

insert into reference.reference_data (key, payload, source, verified_at)
values
  (
    'insurer_catalog',
    $json$[
      "AXA손해보험",
      "DB손해보험",
      "메리츠화재",
      "KDB생명",
      "한화손해보험",
      "교보생명",
      "삼성화재",
      "흥국생명",
      "흥국화재",
      "현대해상화재보험",
      "KB손해보험",
      "미래에셋생명",
      "더케이손해보험",
      "롯데손해보험",
      "캐롯손해보험",
      "메트라이프생명",
      "하나손해보험",
      "MG손해보험",
      "예별손해보험",
      "NH농협생명",
      "NH농협손해보험",
      "AIA생명",
      "ABL생명",
      "커버리샘플생명",
      "커버리샘플손해보험"
    ]$json$::jsonb,
    'local_sample_seed',
    '2026-07-27 00:00:00+09'::timestamptz
  ),
  (
    'essential_coverage_guides',
    $json${
      "sources": [
        {
          "id": "local_essential_coverage_guide",
          "label": "Coverly 로컬 점검 가이드",
          "url": "https://usecoverly.xyz/",
          "published_at": "2026-07-27",
          "reliability": "private_guidance",
          "caveat": "로컬 기능 확인용 범위이며 개인별 적정 보장 기준이 아닙니다."
        }
      ],
      "items": [
        {
          "kind": "death",
          "reference_min_amount": 10000000,
          "reference_max_amount": 20000000,
          "basis": "장례비와 초기 정리 비용을 확인하는 로컬 점검 범위",
          "source_ids": ["local_essential_coverage_guide"]
        },
        {
          "kind": "cancer",
          "reference_min_amount": 30000000,
          "reference_max_amount": 50000000,
          "basis": "암 진단비를 확인하는 로컬 점검 범위",
          "source_ids": ["local_essential_coverage_guide"]
        },
        {
          "kind": "cerebrovascular",
          "reference_min_amount": 30000000,
          "reference_max_amount": 30000000,
          "basis": "뇌혈관질환 진단비를 확인하는 로컬 점검 범위",
          "source_ids": ["local_essential_coverage_guide"]
        },
        {
          "kind": "ischemic_heart",
          "reference_min_amount": 20000000,
          "reference_max_amount": 30000000,
          "basis": "허혈성심질환 진단비를 확인하는 로컬 점검 범위",
          "source_ids": ["local_essential_coverage_guide"]
        },
        {
          "kind": "medical_indemnity",
          "reference_min_amount": null,
          "reference_max_amount": null,
          "basis": "실손의료보험은 금액보다 가입 여부와 중복 여부를 확인",
          "source_ids": ["local_essential_coverage_guide"]
        }
      ]
    }$json$::jsonb,
    'local_sample_seed',
    '2026-07-27 00:00:00+09'::timestamptz
  ),
  (
    'death_benefit_guides',
    $json${
      "sources": [
        {
          "id": "local_death_benefit_guide",
          "label": "Coverly 로컬 사망 보장 가이드",
          "url": "https://usecoverly.xyz/",
          "published_at": "2026-07-27",
          "reliability": "private_guidance",
          "caveat": "로컬 기능 확인용 범위이며 개인별 적정 사망보험금 기준이 아닙니다."
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
          "reason": "장례비와 초기 정리 비용을 중심으로 확인합니다.",
          "source_ids": ["local_death_benefit_guide"]
        },
        {
          "has_dependent_family": true,
          "has_minor_children": false,
          "has_major_debt": false,
          "situation": "가족이 소득에 의존하는 경우",
          "amount_label": "5천만~1.5억 원",
          "min_amount": 50000000,
          "max_amount": 150000000,
          "reason": "일정 기간의 가족 생활비 공백을 함께 확인합니다.",
          "source_ids": ["local_death_benefit_guide"]
        },
        {
          "has_dependent_family": false,
          "has_minor_children": true,
          "has_major_debt": false,
          "situation": "미성년 자녀가 있는 경우",
          "amount_label": "1억~2억 원",
          "min_amount": 100000000,
          "max_amount": 200000000,
          "reason": "자녀 양육비와 교육비 공백을 함께 확인합니다.",
          "source_ids": ["local_death_benefit_guide"]
        },
        {
          "has_dependent_family": true,
          "has_minor_children": true,
          "has_major_debt": false,
          "situation": "가족 생활비와 자녀 양육비가 필요한 경우",
          "amount_label": "2억~3억 원",
          "min_amount": 200000000,
          "max_amount": 300000000,
          "reason": "생활비와 자녀 양육비 공백을 함께 확인합니다.",
          "source_ids": ["local_death_benefit_guide"]
        },
        {
          "has_dependent_family": false,
          "has_minor_children": false,
          "has_major_debt": true,
          "situation": "큰 부채가 있는 경우",
          "amount_label": "5천만~1.5억 원 + 부채 고려",
          "min_amount": 50000000,
          "max_amount": 150000000,
          "reason": "기본 정리 비용과 남은 부채를 함께 확인합니다.",
          "source_ids": ["local_death_benefit_guide"]
        },
        {
          "has_dependent_family": true,
          "has_minor_children": false,
          "has_major_debt": true,
          "situation": "가족 생활비와 부채가 함께 남는 경우",
          "amount_label": "1.5억~3억 원",
          "min_amount": 150000000,
          "max_amount": 300000000,
          "reason": "가족 생활비와 대출 상환 부담을 함께 확인합니다.",
          "source_ids": ["local_death_benefit_guide"]
        },
        {
          "has_dependent_family": false,
          "has_minor_children": true,
          "has_major_debt": true,
          "situation": "자녀 양육비와 부채가 함께 남는 경우",
          "amount_label": "2억~4억 원",
          "min_amount": 200000000,
          "max_amount": 400000000,
          "reason": "자녀 양육비와 대출 상환 부담을 함께 확인합니다.",
          "source_ids": ["local_death_benefit_guide"]
        },
        {
          "has_dependent_family": true,
          "has_minor_children": true,
          "has_major_debt": true,
          "situation": "가족 생활비, 자녀 양육비, 부채가 모두 남는 경우",
          "amount_label": "3억~5억 원",
          "min_amount": 300000000,
          "max_amount": 500000000,
          "reason": "생활비, 자녀 양육비, 대출 상환 부담을 함께 확인합니다.",
          "source_ids": ["local_death_benefit_guide"]
        }
      ]
    }$json$::jsonb,
    'local_sample_seed',
    '2026-07-27 00:00:00+09'::timestamptz
  ),
  (
    'claim_channels',
    $json${
      "_meta": {
        "설명": "Coverly 샘플 보험증권의 로컬 실행용 보험금 청구 채널",
        "갱신일": "2026-07-27"
      },
      "보험사": [
        {
          "보험사": "NH농협손해보험",
          "고객센터": "1644-9000",
          "홈페이지": "https://www.nhfire.co.kr",
          "청구링크": "https://www.nhfire.co.kr/cyber/acd/AcdSimUserStep1.nhfire",
          "앱": null,
          "비고": null,
          "source": "https://www.nhfire.co.kr/index.nhfire"
        },
        {
          "보험사": "흥국화재",
          "고객센터": "1688-1688",
          "홈페이지": "https://www.heungkukfire.co.kr",
          "청구링크": "https://www.heungkukfire.co.kr/FRW/compensation/carCompInfo.do",
          "앱": null,
          "비고": null,
          "source": "https://www.heungkukfire.co.kr"
        },
        {
          "보험사": "현대해상",
          "고객센터": "1588-5656",
          "홈페이지": "https://www.hi.co.kr",
          "청구링크": "https://www.hi.co.kr",
          "앱": "현대해상 모바일 앱",
          "비고": "홈페이지 > 보험금청구",
          "source": "https://www.hi.co.kr/serviceAction.do?menuId=101233"
        },
        {
          "보험사": "삼성화재",
          "고객센터": "1588-5114",
          "홈페이지": "https://www.samsungfire.com",
          "청구링크": "https://www.samsungfire.com",
          "앱": "삼성화재",
          "비고": "홈페이지 > 보험금청구",
          "source": "https://www.samsungfire.com"
        },
        {
          "보험사": "한화손해보험",
          "고객센터": "1566-8000",
          "홈페이지": "https://www.hwgeneralins.com",
          "청구링크": "https://www.hwgeneralins.com",
          "앱": null,
          "비고": "홈페이지 > 보험금청구",
          "source": "https://www.hwgeneralins.com"
        },
        {
          "보험사": "DB손해보험",
          "고객센터": "1588-0100",
          "홈페이지": "https://www.idbins.com",
          "청구링크": "https://www.idbins.com",
          "앱": "DB손해보험",
          "비고": "홈페이지 > 보험금청구",
          "source": "https://www.idbins.com"
        }
      ],
      "실손의료보험": {
        "이름": "실손24",
        "설명": "병원이 진료비 서류를 보험사로 전송하는 보험개발원의 실손의료보험 청구 서비스",
        "콜센터": "1811-3000",
        "채널": [
          {
            "이름": "실손24 홈페이지",
            "링크": "https://www.silson24.or.kr"
          }
        ]
      }
    }$json$::jsonb,
    'local_sample_seed',
    '2026-07-27 00:00:00+09'::timestamptz
  ),
  (
    'disclosure_links',
    $json${
      "association_links": [
        {
          "kind": "life",
          "name": "생명보험협회 공시실",
          "url": "https://www.klia.or.kr/",
          "description": "생명보험 상품공시와 약관 확인 경로"
        },
        {
          "kind": "non_life",
          "name": "손해보험협회 소비자포털 공시정보",
          "url": "https://consumer.knia.or.kr/disclosure.do",
          "description": "손해보험·자동차보험 상품공시와 약관 확인 경로"
        },
        {
          "kind": "integrated",
          "name": "보험다모아",
          "url": "https://e-insmarket.or.kr/",
          "description": "보험상품 비교공시 경로"
        }
      ]
    }$json$::jsonb,
    'local_sample_seed',
    '2026-07-27 00:00:00+09'::timestamptz
  )
on conflict (key) do nothing;

do $$
declare
  required_key_count integer;
begin
  select count(*)
  into required_key_count
  from reference.reference_data
  where key = any (
    array[
      'claim_channels',
      'death_benefit_guides',
      'disclosure_links',
      'essential_coverage_guides',
      'insurer_catalog'
    ]
  );

  if required_key_count <> 5 then
    raise exception
      'local reference data is incomplete: expected 5 required keys, found %',
      required_key_count;
  end if;
end $$;
