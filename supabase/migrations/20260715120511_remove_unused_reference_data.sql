drop table if exists reference.policy_change_notes;
drop table if exists reference.premium_benchmarks;

delete from reference.sources
where id in (
  'fsc_indemnity_claim_digitization_2023_11',
  'fsc_indemnity_reform_2025_04',
  'kb_think_signalplanner_2025_06'
);
