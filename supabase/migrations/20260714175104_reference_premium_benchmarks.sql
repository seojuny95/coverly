create schema if not exists reference;

create table if not exists reference.sources (
  id text primary key,
  title text not null,
  publisher text not null default '',
  url text not null,
  published_at date not null,
  reliability text not null check (
    reliability in (
      'official',
      'public_research',
      'industry',
      'large_private_analysis',
      'private_guidance'
    )
  ),
  caveat text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

comment on table reference.sources is
  'Structured source metadata for non-RAG benchmark data used in analysis.';
comment on column reference.sources.reliability is
  'Trust tier for product use: official, public_research, industry, large_private_analysis, private_guidance.';
comment on column reference.sources.caveat is
  'User-facing limitation text. Benchmarks must not be treated as adequacy standards.';

create table if not exists reference.premium_benchmarks (
  id bigserial primary key,
  source_id text not null references reference.sources(id),
  age_band_label text not null,
  min_age integer not null check (min_age >= 0),
  max_age integer not null check (max_age >= min_age),
  average_monthly_premium integer not null check (average_monthly_premium >= 0),
  effective_at date not null,
  basis text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (source_id, age_band_label, effective_at)
);

comment on table reference.premium_benchmarks is
  'Age-band monthly premium benchmarks. These are comparison references, not adequacy standards.';
comment on column reference.premium_benchmarks.average_monthly_premium is
  'Average monthly premium in KRW.';
comment on column reference.premium_benchmarks.effective_at is
  'Reference data basis date, not the article publication date.';
comment on column reference.premium_benchmarks.basis is
  'Data population and exclusion notes for this benchmark row.';

create index if not exists premium_benchmarks_age_lookup_idx
  on reference.premium_benchmarks (min_age, max_age, effective_at desc);

insert into reference.sources (
  id,
  title,
  publisher,
  url,
  published_at,
  reliability,
  caveat
) values (
  'kb_think_signalplanner_2025_06',
  '시그널플래너 40만명 연령별 월 평균 보험료 분석',
  'KB의 생각',
  'https://kbthink.com/main/asset-management/insurance/insurance-2-240828.html',
  date '2025-06-16',
  'large_private_analysis',
  '저축성보험을 제외한 2006년 이후 가입자의 월 평균 보험료로, 적정 보험료 기준은 아니에요.'
) on conflict (id) do update set
  title = excluded.title,
  publisher = excluded.publisher,
  url = excluded.url,
  published_at = excluded.published_at,
  reliability = excluded.reliability,
  caveat = excluded.caveat,
  updated_at = now();

insert into reference.premium_benchmarks (
  source_id,
  age_band_label,
  min_age,
  max_age,
  average_monthly_premium,
  effective_at,
  basis
) values
  (
    'kb_think_signalplanner_2025_06',
    '20대',
    20,
    29,
    185650,
    date '2021-08-01',
    '2021년 8월 기준, 2006년 이후 가입 보험, 저축성보험 제외'
  ),
  (
    'kb_think_signalplanner_2025_06',
    '30대',
    30,
    39,
    278395,
    date '2021-08-01',
    '2021년 8월 기준, 2006년 이후 가입 보험, 저축성보험 제외'
  ),
  (
    'kb_think_signalplanner_2025_06',
    '40대',
    40,
    49,
    395661,
    date '2021-08-01',
    '2021년 8월 기준, 2006년 이후 가입 보험, 저축성보험 제외'
  ),
  (
    'kb_think_signalplanner_2025_06',
    '50대',
    50,
    59,
    481036,
    date '2021-08-01',
    '2021년 8월 기준, 2006년 이후 가입 보험, 저축성보험 제외'
  ),
  (
    'kb_think_signalplanner_2025_06',
    '60대',
    60,
    69,
    384043,
    date '2021-08-01',
    '2021년 8월 기준, 2006년 이후 가입 보험, 저축성보험 제외'
  ),
  (
    'kb_think_signalplanner_2025_06',
    '70대 이상',
    70,
    120,
    193168,
    date '2021-08-01',
    '2021년 8월 기준, 2006년 이후 가입 보험, 저축성보험 제외'
  )
on conflict (source_id, age_band_label, effective_at) do update set
  min_age = excluded.min_age,
  max_age = excluded.max_age,
  average_monthly_premium = excluded.average_monthly_premium,
  basis = excluded.basis,
  updated_at = now();
