-- Current Coverly database shape for a brand-new Supabase project.
-- Historical files in supabase/migrations/ are intentionally not replayed here.

\set ON_ERROR_STOP on

create schema if not exists extensions;
create extension if not exists vector with schema extensions;

create schema if not exists reference;
revoke all on schema reference from public, anon, authenticated;

create table reference.sources (
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

create table reference.premium_burden_guides (
  id bigserial primary key,
  income_source_id text not null references reference.sources(id),
  guide_source_id text not null references reference.sources(id),
  age_band_label text not null,
  min_age integer not null check (min_age >= 0),
  max_age integer not null check (max_age >= min_age),
  average_monthly_income integer not null check (average_monthly_income >= 0),
  suggested_min_ratio numeric(4, 3) not null check (suggested_min_ratio >= 0),
  suggested_max_ratio numeric(4, 3) not null check (
    suggested_max_ratio >= suggested_min_ratio
  ),
  effective_at date not null,
  basis text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (age_band_label, effective_at)
);

create index premium_burden_guides_age_lookup_idx
  on reference.premium_burden_guides (min_age, max_age, effective_at desc);
create index premium_burden_guides_income_source_idx
  on reference.premium_burden_guides (income_source_id);
create index premium_burden_guides_guide_source_idx
  on reference.premium_burden_guides (guide_source_id);

create table reference.reference_data (
  key text primary key,
  payload jsonb not null,
  source text not null,
  verified_at timestamptz,
  updated_at timestamptz not null default now(),
  constraint reference_data_key_format check (key ~ '^[a-z][a-z0-9_]*$')
);

create function reference.set_updated_at()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger set_reference_data_updated_at
before update on reference.reference_data
for each row execute function reference.set_updated_at();

comment on table reference.sources is
  'Structured source metadata for non-RAG reference data used in analysis.';
comment on table reference.premium_burden_guides is
  'Age-band income-based premium burden guide. This is not an adequacy rule.';
comment on table reference.reference_data is
  'Keyed operational reference payloads used by Coverly analysis.';

alter table reference.sources enable row level security;
alter table reference.premium_burden_guides enable row level security;
alter table reference.reference_data enable row level security;

revoke all on all tables in schema reference from public, anon, authenticated;
revoke all on all sequences in schema reference from public, anon, authenticated;
revoke all on all functions in schema reference from public, anon, authenticated;
alter default privileges in schema reference
  revoke all on tables from public, anon, authenticated;
alter default privileges in schema reference
  revoke all on sequences from public, anon, authenticated;
alter default privileges in schema reference
  revoke execute on functions from public, anon, authenticated;

create schema if not exists private;
revoke all on schema private from public, anon, authenticated;

create table private.portfolio_sessions (
  id uuid primary key,
  created_at timestamptz not null,
  expires_at timestamptz not null,
  max_expires_at timestamptz not null,
  version bigint not null default 0,
  analysis_context_hash text,
  analysis_version bigint,
  analysis_result jsonb,
  counsel_turns_used bigint not null default 0,
  constraint portfolio_session_expiry_order
    check (created_at <= expires_at and expires_at <= max_expires_at),
  constraint portfolio_session_counsel_turns_not_negative
    check (counsel_turns_used >= 0)
);

create table private.policy_documents (
  id uuid primary key,
  portfolio_session_id uuid not null
    references private.portfolio_sessions(id) on delete cascade,
  structured_policy jsonb not null,
  rag_session_id text,
  created_at timestamptz not null default now()
);

create table private.policy_document_tombstones (
  portfolio_session_id uuid not null
    references private.portfolio_sessions(id) on delete cascade,
  document_id uuid not null,
  created_at timestamptz not null default now(),
  primary key (portfolio_session_id, document_id)
);

create table private.policy_document_reservations (
  portfolio_session_id uuid not null
    references private.portfolio_sessions(id) on delete cascade,
  document_id uuid not null,
  reservation_id uuid not null unique,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null,
  primary key (portfolio_session_id, document_id)
);

create index policy_documents_portfolio_session_id_idx
  on private.policy_documents (portfolio_session_id, created_at, id);
create index portfolio_sessions_max_expires_at_idx
  on private.portfolio_sessions (max_expires_at);

comment on table private.portfolio_sessions is
  'Short-lived server-side portfolio sessions addressed by signed bearer tokens.';
comment on column private.portfolio_sessions.counsel_turns_used is
  '이 세션에서 사용한 상담 질문 수. 증권을 추가해도 초기화되지 않는다.';
comment on table private.policy_documents is
  'PII-minimized structured policy facts and internal RAG document references.';
comment on table private.policy_document_tombstones is
  'Cancelled document IDs that reject late upload completions.';
comment on table private.policy_document_reservations is
  'Document slots reserved before policy parsing.';

alter table private.portfolio_sessions enable row level security;
alter table private.policy_documents enable row level security;
alter table private.policy_document_tombstones enable row level security;
alter table private.policy_document_reservations enable row level security;

revoke all on all tables in schema private from public, anon, authenticated;
revoke all on all sequences in schema private from public, anon, authenticated;
alter default privileges in schema private
  revoke all on tables from public, anon, authenticated;
alter default privileges in schema private
  revoke all on sequences from public, anon, authenticated;
alter default privileges in schema private
  revoke execute on functions from public, anon, authenticated;

create table public.policy_rag_chunks (
  id text primary key,
  session_id text not null,
  chunk_index integer not null,
  content_type text not null check (content_type in ('text', 'table')),
  content text not null,
  embedding extensions.vector(1536) not null,
  table_index integer,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null
);

create index policy_rag_chunks_session_idx
  on public.policy_rag_chunks (session_id, expires_at);
create index policy_rag_chunks_expires_at_idx
  on public.policy_rag_chunks (expires_at);
create index policy_rag_chunks_embedding_idx
  on public.policy_rag_chunks
  using hnsw (embedding extensions.vector_cosine_ops);

alter table public.policy_rag_chunks enable row level security;
revoke all on public.policy_rag_chunks from anon, authenticated;
