alter table private.portfolio_sessions
  add column portfolio_kind text not null default 'uploaded',
  add constraint portfolio_sessions_kind_check
    check (portfolio_kind in ('uploaded', 'sample'));

create table private.portfolio_analysis_cache (
  portfolio_session_id uuid not null
    references private.portfolio_sessions(id) on delete cascade,
  portfolio_version bigint not null,
  context_hash text not null,
  analysis_result jsonb not null,
  created_at timestamptz not null default now(),
  primary key (portfolio_session_id, portfolio_version, context_hash)
);

insert into private.portfolio_analysis_cache (
  portfolio_session_id,
  portfolio_version,
  context_hash,
  analysis_result
)
select id, analysis_version, analysis_context_hash, analysis_result
from private.portfolio_sessions
where analysis_version is not null
  and analysis_context_hash is not null
  and analysis_result is not null;

alter table private.portfolio_sessions
  drop column analysis_context_hash,
  drop column analysis_version,
  drop column analysis_result;

alter table private.portfolio_analysis_cache enable row level security;
revoke all on private.portfolio_analysis_cache from public, anon, authenticated;

comment on column private.portfolio_sessions.portfolio_kind is
  'Whether the session contains user-uploaded policies or the immutable demo sample.';
comment on table private.portfolio_analysis_cache is
  'Context-specific cached portfolio analyses, including precomputed sample results.';
