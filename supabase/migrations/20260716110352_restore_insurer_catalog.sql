do $$
declare
  insurer_catalog jsonb := $json$[
    "AXA손해보험",
    "DB손해보험",
    "메리츠화재",
    "KDB생명",
    "한화손해보험",
    "교보생명",
    "삼성화재",
    "흥국생명",
    "흥국화재",
    "현대해상화재보험",
    "KB손해보험",
    "미래에셋생명",
    "더케이손해보험",
    "롯데손해보험",
    "캐롯손해보험",
    "메트라이프생명",
    "하나손해보험",
    "MG손해보험",
    "예별손해보험",
    "NH농협생명",
    "NH농협손해보험",
    "AIA생명",
    "ABL생명"
  ]$json$::jsonb;
begin
  if jsonb_array_length(insurer_catalog) <> 23 then
    raise exception 'expected 23 verified insurers';
  end if;

  insert into reference.reference_data (key, payload, source, verified_at)
  values (
    'insurer_catalog',
    insurer_catalog,
    'user_verified_insurer_catalog',
    now()
  )
  on conflict (key) do update set
    payload = excluded.payload,
    source = excluded.source,
    verified_at = excluded.verified_at,
    updated_at = now();
end $$;
