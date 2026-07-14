create table if not exists reference.policy_change_notes (
  id text primary key,
  source_id text not null references reference.sources(id),
  title text not null,
  summary text not null,
  user_impact text not null,
  related_tags text[] not null default '{}',
  effective_from date,
  applies_to text not null default '',
  display_order integer not null default 100,
  active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

comment on table reference.policy_change_notes is
  'Structured official policy changes that may affect existing insurance analysis.';
comment on column reference.policy_change_notes.related_tags is
  'Coverage tags used by the backend to show only relevant policy changes.';
comment on column reference.policy_change_notes.user_impact is
  'User-facing plain-language impact. Must not recommend product switching.';

create index if not exists policy_change_notes_active_order_idx
  on reference.policy_change_notes (active, display_order, effective_from desc);

create index if not exists policy_change_notes_related_tags_idx
  on reference.policy_change_notes using gin (related_tags);

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
    'fsc_indemnity_reform_2025_04',
    '실손의료보험 개혁방안 보도자료',
    '금융위원회',
    'https://www.fsc.go.kr/no010101/84272',
    date '2025-04-01',
    'official',
    '제도 방향과 시행 예정 사항은 후속 세부방안과 실제 약관에 따라 달라질 수 있어요.'
  ),
  (
    'fsc_indemnity_claim_digitization_2023_11',
    '실손보험 청구 전산화 카드뉴스',
    '금융위원회',
    'https://www.fsc.go.kr/edu/cardnews?cnId=1976',
    date '2023-11-20',
    'official',
    '의료기관 참여 여부와 보험회사 시스템에 따라 실제 이용 가능 범위가 달라질 수 있어요.'
  )
on conflict (id) do update set
  title = excluded.title,
  publisher = excluded.publisher,
  url = excluded.url,
  published_at = excluded.published_at,
  reliability = excluded.reliability,
  caveat = excluded.caveat,
  updated_at = now();

insert into reference.policy_change_notes (
  id,
  source_id,
  title,
  summary,
  user_impact,
  related_tags,
  effective_from,
  applies_to,
  display_order
) values
  (
    'indemnity_claim_digitization_clinics_pharmacies_2025',
    'fsc_indemnity_claim_digitization_2023_11',
    '실손보험 청구 전산화가 의원·약국까지 확대 예정이에요',
    '병원이나 약국에 서류 전송을 요청하면 보험회사로 전자문서가 전달되는 방식이에요.',
    '실손 담보가 있다면 소액 병원비도 청구를 놓치지 않았는지 확인하기 쉬워질 수 있어요.',
    array['실손의료', '청구'],
    date '2025-10-25',
    '의원급 의료기관과 약국의 실손보험 청구',
    10
  ),
  (
    'indemnity_reform_5th_generation_2026',
    'fsc_indemnity_reform_2025_04',
    '실손보험은 급여·중증 중심으로 개편이 진행 중이에요',
    '금융위원회는 실손보험을 급여 의료비와 중증 질환 치료비 중심으로 개편하는 방안을 발표했어요.',
    '실손 담보가 있거나 새로 전환·재가입을 검토할 때는 기존 세대 약관과 새 약관의 자기부담, 비급여 한도, 보장 범위를 비교해야 해요.',
    array['실손의료', '비급여', '제도변화'],
    date '2026-07-01',
    '실손보험 신규 가입과 약관변경 대상자',
    20
  )
on conflict (id) do update set
  source_id = excluded.source_id,
  title = excluded.title,
  summary = excluded.summary,
  user_impact = excluded.user_impact,
  related_tags = excluded.related_tags,
  effective_from = excluded.effective_from,
  applies_to = excluded.applies_to,
  display_order = excluded.display_order,
  active = true,
  updated_at = now();

alter table reference.policy_change_notes enable row level security;

revoke all on reference.policy_change_notes from anon, authenticated;
