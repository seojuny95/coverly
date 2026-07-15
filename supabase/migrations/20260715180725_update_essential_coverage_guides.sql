do $$
declare
  target_table regclass := coalesce(
    to_regclass('reference.reference_data'),
    to_regclass('coverly.reference_data')
  );
  essential_coverage_guides jsonb := '{
    "items": [
      {
        "kind": "death",
        "basis": "장례비와 초기 정리 비용을 먼저 보는 점검용 범위",
        "reference_min_amount": 10000000,
        "reference_max_amount": 20000000,
        "source_ids": ["kca_funeral_cost_2004"]
      },
      {
        "kind": "cancer",
        "basis": "암 진단비는 치료 중 쉬는 기간의 생활비 성격까지 고려하는 기본 범위",
        "reference_min_amount": 30000000,
        "reference_max_amount": 50000000,
        "source_ids": ["bizwatch_cancer_diagnosis_2024_07", "banksalad_three_diagnosis_2026"]
      },
      {
        "kind": "cerebrovascular",
        "basis": "뇌혈관질환 진단비는 재활, 간병, 후유장해 가능성을 고려하는 기본 범위",
        "reference_min_amount": 10000000,
        "reference_max_amount": 20000000,
        "source_ids": ["banksalad_three_diagnosis_2026"]
      },
      {
        "kind": "ischemic_heart",
        "basis": "심장질환 진단비는 시술, 수술, 입원으로 생길 수 있는 소득 공백을 고려하는 기본 범위",
        "reference_min_amount": 10000000,
        "reference_max_amount": 20000000,
        "source_ids": ["banksalad_three_diagnosis_2026"]
      },
      {
        "kind": "indemnity",
        "basis": "실손은 금액보다 가입 여부, 세대, 자기부담금, 중복 여부를 확인",
        "reference_min_amount": null,
        "reference_max_amount": null,
        "source_ids": ["silson24_official"]
      }
    ],
    "sources": [
      {
        "id": "kca_funeral_cost_2004",
        "label": "한국소비자원 · 평균 장례비용 조사",
        "url": "https://www.kca.go.kr/home/sub.do?menukey=4002&mode=view&no=1000396173&page=148",
        "published_at": "2004-09-22",
        "reliability": "official",
        "caveat": "장례비용은 시기, 지역, 장례 방식에 따라 달라질 수 있어요."
      },
      {
        "id": "bizwatch_cancer_diagnosis_2024_07",
        "label": "비즈워치 · 암 진단비 평균 범위",
        "url": "https://news.bizwatch.co.kr/article/finance/2024/07/05/0038",
        "published_at": "2024-07-06",
        "reliability": "private_guidance",
        "caveat": "암 진단비 금액은 소득, 가족 부양, 보험료 부담에 따라 달라질 수 있어요."
      },
      {
        "id": "banksalad_three_diagnosis_2026",
        "label": "뱅크샐러드 · 3대 진단비 구성 예시",
        "url": "https://www.banksalad.com/articles/%EB%B3%B4%ED%97%98-%EC%A2%85%ED%95%A9%EB%B3%B4%ED%97%98-%EC%A7%88%EB%B3%B4%ED%97%98",
        "published_at": "2026-07-01",
        "reliability": "private_guidance",
        "caveat": "구성 예시는 상품과 개인 상황에 따라 달라질 수 있어요."
      },
      {
        "id": "silson24_official",
        "label": "실손24 · 서비스 안내",
        "url": "https://www.silson24.or.kr",
        "published_at": "2025-01-01",
        "reliability": "official",
        "caveat": "실손 청구 가능 범위는 의료기관과 보험회사 시스템에 따라 달라질 수 있어요."
      }
    ]
  }'::jsonb;
begin
  if target_table is null then
    raise exception 'reference data table is missing';
  end if;

  execute format(
    'insert into %s (key, payload, source, verified_at)
     values ($1, $2, $3, $4)
     on conflict (key) do update
     set payload = excluded.payload,
         source = excluded.source,
         verified_at = excluded.verified_at',
    target_table
  )
  using
    'essential_coverage_guides',
    essential_coverage_guides,
    'user_verified_essential_coverage_guides',
    '2026-07-16 00:00:00+09'::timestamptz;

  if to_regclass('reference.reference_data') is not null then
    delete from reference.reference_data
    where key in (
      'classification_rules',
      'coverage_matching_rules',
      'insurer_catalog'
    );
  end if;

  if to_regclass('coverly.reference_data') is not null then
    delete from coverly.reference_data
    where key in (
      'classification_rules',
      'coverage_matching_rules',
      'insurer_catalog'
    );
  end if;
end $$;
