create table if not exists reference.reference_data (
  key text primary key,
  payload jsonb not null,
  source text not null,
  verified_at timestamptz,
  updated_at timestamptz not null default now(),
  constraint reference_data_key_format check (key ~ '^[a-z][a-z0-9_]*$')
);

comment on table reference.reference_data is
  'Keyed operational reference payloads used by Coverly analysis.';
comment on column reference.reference_data.source is
  'Dataset provenance label for this payload.';
comment on column reference.reference_data.verified_at is
  'Timestamp when the payload was last verified for product use.';

alter table reference.reference_data enable row level security;

revoke all on reference.reference_data from public, anon, authenticated;

create or replace function reference.set_updated_at()
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

revoke all on function reference.set_updated_at() from public, anon, authenticated;

drop trigger if exists set_reference_data_updated_at on reference.reference_data;

create trigger set_reference_data_updated_at
before update on reference.reference_data
for each row execute function reference.set_updated_at();

insert into reference.reference_data (key, payload, source, verified_at, updated_at)
select key, payload, source, verified_at, updated_at
from coverly.reference_data
on conflict (key) do update set
  payload = excluded.payload,
  source = excluded.source,
  verified_at = excluded.verified_at,
  updated_at = excluded.updated_at;

drop trigger if exists set_reference_data_updated_at on coverly.reference_data;
drop table if exists coverly.reference_data;
drop function if exists coverly.set_updated_at();
drop schema if exists coverly;
