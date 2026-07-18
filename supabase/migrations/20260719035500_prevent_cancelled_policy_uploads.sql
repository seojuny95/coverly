create table private.policy_document_tombstones (
  portfolio_session_id uuid not null
    references private.portfolio_sessions(id) on delete cascade,
  document_id uuid not null,
  created_at timestamptz not null default now(),
  primary key (portfolio_session_id, document_id)
);

alter table private.policy_document_tombstones enable row level security;

revoke all on private.policy_document_tombstones from public, anon, authenticated;

comment on table private.policy_document_tombstones is
  'Cancelled client-assigned document IDs that must not be stored by late upload completions.';
