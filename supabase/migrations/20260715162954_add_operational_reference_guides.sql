insert into coverly.reference_data (key, payload, source, verified_at)
values
  (
    'insurer_catalog',
    $json$[
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
    ]$json$::jsonb,
    'user_verified_insurer_catalog',
    now()
  ),
  (
    'essential_coverage_guides',
    $json${
      "sources": [
        {
          "id": "kca_funeral_cost_2004",
          "label": "한국소비자원 · 평균 장례비용 조사",
          "url": "https://www.kca.go.kr/home/sub.do?menukey=4002&mode=view&no=1000396173&page=148",
          "published_at": "2004-09-22",
          "reliability": "official",
          "caveat": "장례비용은 시기, 지역, 장례 방식에 따라 달라질 수 있어요."
        },
        {
          "id": "signalplanner_diagnosis_article",
          "label": "시그널플래너 · 3대 진단비 설명",
          "url": "https://blog.signalplanner.co.kr/5344/",
          "published_at": "2022-01-01",
          "reliability": "private_guidance",
          "caveat": "진단비 금액은 개인 상황과 상품 조건에 따라 달라질 수 있어요."
        },
        {
          "id": "silson24_official",
          "label": "실손24 · 서비스 안내",
          "url": "https://www.silson24.or.kr",
          "published_at": "2025-01-01",
          "reliability": "official",
          "caveat": "실손 청구 가능 범위는 의료기관과 보험회사 시스템에 따라 달라질 수 있어요."
        }
      ],
      "items": [
        {
          "kind": "death",
          "reference_min_amount": 10000000,
          "reference_max_amount": 20000000,
          "basis": "장례비와 초기 정리 비용을 먼저 보는 점검용 범위",
          "source_ids": ["kca_funeral_cost_2004"]
        },
        {
          "kind": "cancer",
          "reference_min_amount": 30000000,
          "reference_max_amount": 50000000,
          "basis": "3대 진단비 점검용 범위",
          "source_ids": ["signalplanner_diagnosis_article"]
        },
        {
          "kind": "cerebrovascular",
          "reference_min_amount": 30000000,
          "reference_max_amount": 30000000,
          "basis": "3대 진단비 점검용 범위",
          "source_ids": ["signalplanner_diagnosis_article"]
        },
        {
          "kind": "ischemic_heart",
          "reference_min_amount": 20000000,
          "reference_max_amount": 30000000,
          "basis": "3대 진단비 점검용 범위",
          "source_ids": ["signalplanner_diagnosis_article"]
        },
        {
          "kind": "indemnity",
          "reference_min_amount": null,
          "reference_max_amount": null,
          "basis": "실손은 금액보다 가입 여부, 세대, 자기부담금, 중복 여부를 확인",
          "source_ids": ["silson24_official"]
        }
      ]
    }$json$::jsonb,
    'user_verified_essential_coverage_guides',
    now()
  )
on conflict (key) do update set
  payload = excluded.payload,
  source = excluded.source,
  verified_at = excluded.verified_at,
  updated_at = now();
