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
  constraint portfolio_session_expiry_order
    check (created_at <= expires_at and expires_at <= max_expires_at)
);

create table private.policy_documents (
  id uuid primary key,
  portfolio_session_id uuid not null
    references private.portfolio_sessions(id) on delete cascade,
  structured_policy jsonb not null,
  rag_session_id text,
  created_at timestamptz not null default now()
);

create index policy_documents_portfolio_session_id_idx
  on private.policy_documents (portfolio_session_id, created_at, id);

create index portfolio_sessions_max_expires_at_idx
  on private.portfolio_sessions (max_expires_at);

alter table private.portfolio_sessions enable row level security;
alter table private.policy_documents enable row level security;

revoke all on private.portfolio_sessions from public, anon, authenticated;
revoke all on private.policy_documents from public, anon, authenticated;

alter default privileges in schema private
  revoke all on tables from public, anon, authenticated;
alter default privileges in schema private
  revoke all on sequences from public, anon, authenticated;
alter default privileges in schema private
  revoke execute on functions from public, anon, authenticated;

comment on table private.portfolio_sessions is
  'Short-lived server-side portfolio sessions addressed by signed bearer tokens.';
comment on table private.policy_documents is
  'PII-minimized structured policy facts and internal RAG document references.';
