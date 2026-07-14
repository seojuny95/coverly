alter table reference.sources enable row level security;
alter table reference.premium_benchmarks enable row level security;

revoke all on schema reference from anon, authenticated;
revoke all on all tables in schema reference from anon, authenticated;
revoke all on all sequences in schema reference from anon, authenticated;

alter default privileges in schema reference
  revoke all on tables from anon, authenticated;

alter default privileges in schema reference
  revoke all on sequences from anon, authenticated;
