create schema if not exists coverly;

revoke all on schema coverly from public, anon, authenticated;

create table coverly.reference_data (
    key text primary key,
    payload jsonb not null,
    source text not null,
    verified_at timestamptz,
    updated_at timestamptz not null default now(),
    constraint reference_data_key_format check (key ~ '^[a-z][a-z0-9_]*$')
);

alter table coverly.reference_data enable row level security;

revoke all on coverly.reference_data from public, anon, authenticated;

create function coverly.set_updated_at()
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

revoke all on function coverly.set_updated_at() from public, anon, authenticated;

create trigger set_reference_data_updated_at
before update on coverly.reference_data
for each row execute function coverly.set_updated_at();
