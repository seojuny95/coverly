drop table if exists public.official_rag_chunks;

do $$
begin
  if to_regclass('public.data_official_rag_chunks_staging_embedding_idx') is not null then
    drop index if exists public.data_official_rag_chunks_embedding_idx;
    alter index public.data_official_rag_chunks_staging_embedding_idx
      rename to data_official_rag_chunks_embedding_idx;
  end if;
end $$;

do $$
begin
  if exists (
    select 1
    from pg_constraint
    where conrelid = to_regclass('public.data_official_rag_chunks')
      and conname = 'data_official_rag_chunks_staging_pkey'
  ) then
    alter table public.data_official_rag_chunks
      rename constraint data_official_rag_chunks_staging_pkey
      to data_official_rag_chunks_pkey;
  end if;
end $$;

do $$
begin
  if to_regclass('public.official_rag_chunks_staging_idx') is not null then
    drop index if exists public.data_official_rag_chunks_text_search_tsv_idx;
    alter index public.official_rag_chunks_staging_idx
      rename to data_official_rag_chunks_text_search_tsv_idx;
  end if;
end $$;

do $$
begin
  if to_regclass('public.official_rag_chunks_staging_idx_1') is not null then
    drop index if exists public.data_official_rag_chunks_ref_doc_id_idx;
    alter index public.official_rag_chunks_staging_idx_1
      rename to data_official_rag_chunks_ref_doc_id_idx;
  end if;
end $$;
