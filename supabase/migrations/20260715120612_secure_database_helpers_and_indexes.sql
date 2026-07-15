revoke execute on function public.rls_auto_enable() from public, anon, authenticated;

drop index if exists public.data_official_rag_chunks_staging_embedding_idx;

create index if not exists premium_burden_guides_income_source_idx
  on reference.premium_burden_guides (income_source_id);

create index if not exists premium_burden_guides_guide_source_idx
  on reference.premium_burden_guides (guide_source_id);
