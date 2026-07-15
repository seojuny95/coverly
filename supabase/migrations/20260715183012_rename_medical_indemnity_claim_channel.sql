do $$
declare
  claim_channels jsonb;
begin
  select payload
  into claim_channels
  from reference.reference_data
  where key = 'claim_channels';

  if claim_channels is null then
    raise exception 'claim_channels reference data is missing';
  end if;
  if not (claim_channels ? '실손') or (claim_channels ? '실손의료보험') then
    raise exception 'claim_channels must contain only the legacy medical indemnity key';
  end if;

  update reference.reference_data
  set payload = (payload - '실손') || jsonb_build_object(
    '실손의료보험',
    jsonb_set(
      payload -> '실손',
      '{설명}',
      to_jsonb(
        '병원이 진료비 서류를 보험사로 자동 전송해, 서류 없이 실손의료보험금을 청구하는 공식 서비스(보험개발원). 전 요양기관(병원·의원·약국) 대상.'::text
      )
    )
  )
  where key = 'claim_channels';
end $$;
