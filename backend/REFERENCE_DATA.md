# 참조 및 세션 데이터 경계

이 문서는 보험 분석에 쓰이는 참조 데이터의 소유권과 배포 경계를 정의한다. 기준일과 출처가 있는 사실은 시간이 지나면 바뀔 수 있으므로 코드의 상수로 굳히지 않는다. Supabase migration은 DB의 소스 오브 트루스로 유지하고, 기존 마이그레이션 기록은 보존한다.

## 소유권

| 영역 | 소유하는 것 | 원칙 |
| --- | --- | --- |
| Supabase | 출처·기준일이 있는 변경 가능한 참조 사실, RAG 데이터, 짧게 유지하는 포트폴리오 세션 | 운영 데이터와 서버 세션의 원본이다. 마이그레이션 기록이 스키마와 이력의 기준이다. |
| 서버 코드 | PDF 파싱, 분류, 담보 매칭, grounding·안전 필터, 집계, 실패·degrade 정책 | 입력을 구조화하고 판단 절차를 결정한다. 데이터 갱신을 코드 배포로 대체하지 않는다. |
| 프론트엔드 | 서버 응답의 표시와 사용자 상호작용 | 보험 사실이나 LLM 총평을 임의로 만들어내지 않는다. |

`classification_rules`와 `coverage_matching_rules`는 서버 동작을 결정하는 규칙이므로 코드 배포와 함께 버전 관리한다. `claim_channels`, `death_benefit_guides`, `disclosure_links`, `insurer_catalog`, `essential_coverage_guides`는 Supabase `reference.reference_data`가 단일 원본이다. 서버 코드에는 같은 데이터를 bundled JSON이나 fallback 상수로 보관하지 않는다. DB 조회 실패·스키마 불일치·필수 row 누락은 전체 분석을 실패시키는 참조 데이터 오류로 처리한다. 공식 RAG 인덱싱에 쓰는 데이터 적재/갱신 잡은 현재 RAG 인덱싱 경로에서 계속 호출 가능하지만, 별도 `jobs/` 디렉터리가 있다고 문서화하지 않는다.

LLM 총평은 서버가 근거를 구성한 뒤 생성하고 검증해야 한다. 프론트엔드의 synthetic fallback, 임의 요약, 누락 응답을 대체하는 문구 생성은 금지한다.

## 현재 테이블 사용 현황

| 테이블 | 상태 | 용도와 경계 |
| --- | --- | --- |
| `public.data_official_rag_chunks` | current | 현재 서버 설정(`RAG_PG_TABLE=official_rag_chunks`)을 LlamaIndex PGVectorStore가 물리 테이블로 변환해 읽는 공식 약관·제도 RAG 청크. 서버 전용이며 브라우저 역할에는 권한을 주지 않는다. |
| `public.policy_rag_chunks` | current ephemeral | 업로드한 증권 원문의 검색용 청크. 내부 문서 RAG ID로 연결하고 만료·삭제를 전제로 한다. 서버 전용이다. |
| `private.portfolio_sessions` | current ephemeral | 서명된 단일 토큰으로 접근하는 포트폴리오 세션. 만료 시각, 데이터 버전, 분석 결과 캐시를 보관한다. |
| `private.policy_documents` | current ephemeral | 포트폴리오 세션에 속한 PII 최소화 구조화 증권, 분석 상태, 내부 RAG 참조를 보관한다. 세션 삭제 시 함께 삭제된다. |
| `private.policy_document_reservations` | current ephemeral | PDF 파싱 전에 문서 슬롯을 원자적으로 확보하는 단기 lease. 세션·문서 ID와 예약 소유자 ID, 만료 시각을 보관하며 완료·실패·취소 또는 만료 정리 시 제거된다. |
| `reference.reference_data` | current | `claim_channels`, `death_benefit_guides`, `disclosure_links`, `insurer_catalog`, `essential_coverage_guides` 운영 참조 데이터의 DB 원본 |
| `reference.sources` | current | 구조화된 참조 테이블이 공유하는 출처 메타데이터 |
| `reference.premium_burden_guides` | current | 보험료 부담 가이드의 운영 기준. 스키마·기준일을 함께 관리한다. |
| `official_rag_chunks` | removed | 중복된 legacy official RAG 테이블. 현재 runtime은 `data_official_rag_chunks`만 사용하므로 cleanup migration으로 제거했다. |
| `coverly.reference_data` | removed | `reference.reference_data`로 이전했다. |
| `premium_benchmarks` | removed | 현재 계약과 달랐던 기존 보험료 벤치마크 테이블. cleanup migration으로 제거했다. |
| `policy_change_notes` | removed | 제거된 구 분석 API 전용 제도 변경 메모. cleanup migration으로 제거했다. |

상태 표는 마이그레이션 적용 이력이 아니라 현재 사용 계약을 기록한다. migration은 이미 적용된 이력이므로 삭제하거나 재작성하지 않는다. 잘못된 정의나 중복은 새 migration으로 정리하고, 전환 기간에는 읽기 경로와 영향 범위를 명시한다.

## 새 환경 초기 데이터

`reference.reference_data` migration은 테이블 구조와 이력을 관리한다. `claim_channels`, `death_benefit_guides`, `disclosure_links`, `insurer_catalog`, `essential_coverage_guides`의 실제 payload는 Supabase 운영 데이터로 관리하며, 새 로컬·스테이징 환경도 승인된 DB 작업이나 새 migration으로 같은 row를 준비해야 한다. 서버 repo의 seed 스크립트나 bundled JSON으로 운영 데이터를 복제하지 않는다.

## 포트폴리오 세션 운영 규칙

- 프론트엔드는 서명된 `portfolioSessionToken` 하나와 필요한 문서 ID만 서버에 보낸다. 매 요청마다 모든 구조화 증권을 다시 보내지 않는다.
- `private.policy_documents`에는 분석과 Q&A에 필요한 구조화 사실만 저장한다. 계약자명, 피보험자명, 계약번호, 차량번호 같은 직접 식별자는 저장하지 않고 담보 텍스트도 공통 PII 마스커를 통과시킨다.
- 세션 토큰은 서버가 서명을 검증하며, DB에는 토큰 원문을 저장하지 않는다. `private` 스키마는 `anon`과 `authenticated`에 접근 권한을 주지 않는다.
- 세션은 절대 만료 시각을 넘겨 연장하지 않는다. 만료 세션은 새 세션 생성 시 정리하며, 세션 삭제 시 하위 구조화 증권은 외래키 연쇄 삭제로 함께 제거한다. 증권 RAG 청크는 연결된 내부 RAG ID의 만료·삭제 경로를 따른다.
- 업로드 한도는 PDF 파싱을 시작하기 전에 세션 행 잠금 아래 완료 문서와 유효한 예약을 함께 세어 적용한다. 예약은 설정된 TTL을 넘으면 슬롯 계산에서 제거하며, 동일 문서의 동시 예약·완료 문서 재등록은 충돌로 처리한다.
- 예약 완료·해제는 `reservation_id`가 일치하는 소유자만 수행한다. 만료된 작업이 같은 문서 ID의 새 예약을 완료하거나 해제하는 ABA 상황을 허용하지 않는다. 파싱 실패, 저장 실패, 사용자 취소에서는 예약과 새로 만든 RAG 문서를 정리한다.
- 분석 결과는 세션 데이터 버전과 분석 입력 해시가 모두 같을 때만 재사용한다. 증권 추가나 분석 입력 변경 시 다시 계산한다.

## 출처 등급

참조 사실은 화면에 출처 성격을 함께 표시한다. 사용자가 검증한 링크라도 모든 링크가 같은 법적 무게를 갖지는 않기 때문에, 서버 응답은 아래 등급 중 하나를 포함해야 한다.

| 등급 | 화면 표시 | 의미 |
| --- | --- | --- |
| `official` | 공식 출처 | 정부, 공공기관, 공식 서비스 등 1차 출처 |
| `industry` | 협회·공시 출처 | 보험협회, 상품공시, 비교공시 등 업계 공시 출처 |
| `public_research` | 공공 연구 출처 | 공공 연구·통계 기반 출처 |
| `large_private_analysis` | 민간 분석 출처 | 대규모 민간 데이터 분석 또는 리포트 |
| `private_guidance` | 아티클·블로그 출처 | 민간 서비스의 설명 글, 블로그, 가이드 |

## 운영 규칙

- 참조 사실에는 출처와 기준일을 저장하고 응답 근거에 연결한다.
- RAG 검색 결과가 없거나 근거가 부족하면 서버는 확인 불가로 degrade한다.
- 공식 RAG는 `official-sources/source_registry.json`의 `document_type`에 따라 문서 타입별 chunker를 사용한다. 법령 XML은 조문 단위, 표준약관은 상품/특약 섹션과 조항 단위, 자동차보험 표준상품설명서는 설명서 섹션 단위, 일반 소비자 안내자료는 페이지/제목 단위로 나눈 뒤 공통 `RagChunk` 형식으로 저장한다.
- 공식 RAG 운영 index는 `app.rag.official.indexing`으로 staging table에 재적재한 뒤 serving table로 swap한다. swap 이후 live table의 PK/index 이름은 `data_official_rag_chunks_*` 형태로 정규화한다.
- Supabase 소유 참조 데이터에는 서버 bundled fallback을 두지 않는다.
- `claim_channels`, `death_benefit_guides`, `disclosure_links`, `insurer_catalog`, `essential_coverage_guides`가 없거나 읽히지 않으면 전체 분석을 실패시킨다.
- 참조 데이터 스키마 변경은 새 migration과 검증 코드를 함께 추가한다.
