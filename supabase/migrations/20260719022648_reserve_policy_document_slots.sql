create table private.policy_document_reservations (
  portfolio_session_id uuid not null
    references private.portfolio_sessions(id) on delete cascade,
  document_id uuid not null,
  reservation_id uuid not null unique,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null,
  primary key (portfolio_session_id, document_id)
);

alter table private.policy_document_reservations enable row level security;

revoke all on private.policy_document_reservations from public, anon, authenticated;

comment on table private.policy_document_reservations is
  'Document slots reserved before policy parsing begins; removed on completion, failure, or cancellation.';
