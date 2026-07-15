do $$
declare
  legacy_item_count integer;
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
end $$;
