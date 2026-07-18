alter table private.policy_documents
  drop column if exists analysis_status,
  drop column if exists rag_status;
