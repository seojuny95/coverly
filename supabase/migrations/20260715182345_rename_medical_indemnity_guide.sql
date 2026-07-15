do $$
declare
  legacy_item_count integer;
  source_count integer;
begin
  select count(*)
  into legacy_item_count
  from reference.reference_data as data,
       jsonb_array_elements(data.payload -> 'items') as item
  where data.key = 'essential_coverage_guides'
    and item ->> 'kind' = 'indemnity';

  if legacy_item_count <> 1 then
    raise exception
      'expected exactly one indemnity essential coverage guide, found %',
      legacy_item_count;
  end if;

  select count(*)
  into source_count
  from reference.reference_data as data,
       jsonb_array_elements(data.payload -> 'sources') as source_entries(source_item)
  where data.key = 'essential_coverage_guides'
    and source_item ->> 'id' = 'silson24_official';

  if source_count <> 1 then
    raise exception
      'expected exactly one silson24 essential coverage source, found %',
      source_count;
  end if;

  update reference.reference_data as data
  set payload = jsonb_set(
    data.payload,
    '{items}',
    (
      select jsonb_agg(
        case
          when item ->> 'kind' = 'indemnity' then
            jsonb_set(
              jsonb_set(
                item,
                '{kind}',
                to_jsonb('medical_indemnity'::text)
              ),
              '{basis}',
              to_jsonb(
                '실손의료보험은 금액보다 가입 여부, 세대, 자기부담금, 중복 여부를 확인'::text
              )
            )
          else item
        end
        order by ordinal
      )
      from jsonb_array_elements(data.payload -> 'items')
        with ordinality as entries(item, ordinal)
    )
  )
  where data.key = 'essential_coverage_guides';

  update reference.reference_data as data
  set payload = jsonb_set(
    data.payload,
    '{sources}',
    (
      select jsonb_agg(
        case
          when source_item ->> 'id' = 'silson24_official' then
            jsonb_set(
              source_item,
              '{caveat}',
              to_jsonb(
                '실손의료비 청구 가능 범위는 의료기관과 보험회사 시스템에 따라 달라질 수 있어요.'::text
              )
            )
          else source_item
        end
        order by ordinal
      )
      from jsonb_array_elements(data.payload -> 'sources')
        with ordinality as source_entries(source_item, ordinal)
    )
  )
  where data.key = 'essential_coverage_guides';
end $$;
