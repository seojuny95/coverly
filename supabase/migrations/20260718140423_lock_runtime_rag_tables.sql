alter table public.data_official_rag_chunks enable row level security;
alter table public.policy_rag_chunks enable row level security;

revoke all on public.data_official_rag_chunks from anon, authenticated;
revoke all on public.policy_rag_chunks from anon, authenticated;
