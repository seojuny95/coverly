create table if not exists reference.premium_burden_guides (
  id bigserial primary key,
  income_source_id text not null references reference.sources(id),
  guide_source_id text not null references reference.sources(id),
  age_band_label text not null,
  min_age integer not null check (min_age >= 0),
  max_age integer not null check (max_age >= min_age),
  average_monthly_income integer not null check (average_monthly_income >= 0),
  suggested_min_ratio numeric(4, 3) not null check (suggested_min_ratio >= 0),
  suggested_max_ratio numeric(4, 3) not null check (suggested_max_ratio >= suggested_min_ratio),
  effective_at date not null,
  basis text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (age_band_label, effective_at)
);

comment on table reference.premium_burden_guides is
  'Age-band income-based premium burden guide. This is a comparison reference, not an adequacy rule.';
comment on column reference.premium_burden_guides.average_monthly_income is
  'Average monthly income in KRW used for burden-range calculations.';
comment on column reference.premium_burden_guides.suggested_min_ratio is
  'Lower guide ratio (for example, 0.05 means 5 percent of income).';
comment on column reference.premium_burden_guides.suggested_max_ratio is
  'Upper guide ratio (for example, 0.10 means 10 percent of income).';

create index if not exists premium_burden_guides_age_lookup_idx
  on reference.premium_burden_guides (min_age, max_age, effective_at desc);

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
    'https://kosis.kr/statHtml/statHtml.do?sso=ok&returnurl=https%3A%2F%2Fkosis.kr%3A443%2FstatHtml%2FstatHtml.do%3Fconn_path%3DI2%26tblId%3DDT_1EP_2010%26orgId%3D101%26',
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
    '월 소득의 5%~10% 범위는 민간 가이드예요. 적정 보험료의 공식 기준은 아니에요.'
  )
on conflict (id) do update set
  title = excluded.title,
  publisher = excluded.publisher,
  url = excluded.url,
  published_at = excluded.published_at,
  reliability = excluded.reliability,
  caveat = excluded.caveat,
  updated_at = now();

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
  (
    'kosis_income_by_age_2025',
    'banksalad_premium_burden_guide_2025',
    '20~29세',
    20,
    29,
    2630000,
    0.05,
    0.10,
    date '2025-01-01',
    'KOSIS 성별 연령대별 소득 기준 평균 소득에 민간 가이드 5~10%를 적용한 범위'
  ),
  (
    'kosis_income_by_age_2025',
    'banksalad_premium_burden_guide_2025',
    '30~39세',
    30,
    39,
    3860000,
    0.05,
    0.10,
    date '2025-01-01',
    'KOSIS 성별 연령대별 소득 기준 평균 소득에 민간 가이드 5~10%를 적용한 범위'
  ),
  (
    'kosis_income_by_age_2025',
    'banksalad_premium_burden_guide_2025',
    '40~49세',
    40,
    49,
    4510000,
    0.05,
    0.10,
    date '2025-01-01',
    'KOSIS 성별 연령대별 소득 기준 평균 소득에 민간 가이드 5~10%를 적용한 범위'
  ),
  (
    'kosis_income_by_age_2025',
    'banksalad_premium_burden_guide_2025',
    '50~59세',
    50,
    59,
    4290000,
    0.05,
    0.10,
    date '2025-01-01',
    'KOSIS 성별 연령대별 소득 기준 평균 소득에 민간 가이드 5~10%를 적용한 범위'
  ),
  (
    'kosis_income_by_age_2025',
    'banksalad_premium_burden_guide_2025',
    '60세 이상',
    60,
    120,
    2500000,
    0.05,
    0.10,
    date '2025-01-01',
    'KOSIS 성별 연령대별 소득 기준 평균 소득에 민간 가이드 5~10%를 적용한 범위'
  )
on conflict (age_band_label, effective_at) do update set
  income_source_id = excluded.income_source_id,
  guide_source_id = excluded.guide_source_id,
  min_age = excluded.min_age,
  max_age = excluded.max_age,
  average_monthly_income = excluded.average_monthly_income,
  suggested_min_ratio = excluded.suggested_min_ratio,
  suggested_max_ratio = excluded.suggested_max_ratio,
  basis = excluded.basis,
  updated_at = now();

alter table reference.premium_burden_guides enable row level security;

revoke all on reference.premium_burden_guides from anon, authenticated;
