delete from coverly.reference_data
where key in (
  'classification_rules',
  'coverage_matching_rules',
  'insurer_catalog'
);
