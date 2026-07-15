# 참조 데이터 경계

이 문서는 보험 분석에 쓰이는 참조 데이터의 소유권과 배포 경계를 정의한다. 기준일과 출처가 있는 사실은 시간이 지나면 바뀔 수 있으므로 코드의 상수로 굳히지 않는다. Supabase migration은 DB의 소스 오브 트루스로 유지하고, 기존 마이그레이션 기록은 보존한다.

## 소유권

| 영역 | 소유하는 것 | 원칙 |
| --- | --- | --- |
| Supabase | 출처·기준일이 있는 변경 가능한 참조 사실, 공식 약관·제도 RAG 데이터 | 운영 데이터의 원본이다. 내용과 유효기간을 갱신하고 검색 가능하게 유지한다. 마이그레이션 기록이 스키마와 이력의 기준이다. |
| 서버 코드 | PDF 파싱, 분류, 담보 매칭, grounding·안전 필터, 집계, 실패·degrade 정책 | 입력을 구조화하고 판단 절차를 결정한다. 데이터 갱신을 코드 배포로 대체하지 않는다. |
| 프론트엔드 | 서버 응답의 표시와 사용자 상호작용 | 보험 사실이나 LLM 총평을 임의로 만들어내지 않는다. |

`classification_rules`와 `coverage_matching_rules`는 서버 동작을 결정하는 규칙이므로 코드 배포와 함께 버전 관리한다. `claim_channels`와 `disclosure_links`는 Supabase `coverly.reference_data`가 단일 원본이다. 서버 코드에는 같은 데이터를 bundled JSON이나 fallback 상수로 보관하지 않는다. DB 조회 실패·스키마 불일치·필수 row 누락은 전체 분석을 실패시키는 참조 데이터 오류로 처리한다. 공식 RAG 인덱싱에 쓰는 데이터 적재/갱신 잡은 현재 RAG 인덱싱 경로에서 계속 호출 가능하지만, 별도 `jobs/` 디렉터리가 있다고 문서화하지 않는다.

LLM 총평은 서버가 근거를 구성한 뒤 생성하고 검증해야 한다. 프론트엔드의 synthetic fallback, 임의 요약, 누락 응답을 대체하는 문구 생성은 금지한다.

## 현재 테이블 사용 현황

| 테이블 | 상태 | 용도와 경계 |
| --- | --- | --- |
| `data_official_rag_chunks` | current | 출처가 있는 공식 약관·제도 RAG 청크 |
| `policy_rag_chunks` | current ephemeral | 업로드 세션별 RAG 청크. 만료·삭제를 전제로 한다. |
| `official_rag_chunks` | legacy candidate | 기존 공식 RAG 후보. 새 읽기 경로의 기준으로 사용하지 않고 이전·정리 대상을 식별한다. |
| `coverly.reference_data` | current | `claim_channels`, `disclosure_links` 운영 디렉터리의 DB 원본 |
| `premium_burden_guides` | current | 보험료 부담 가이드의 운영 기준. 스키마·기준일을 함께 관리한다. |
| `premium_benchmarks` | removed | 현재 계약과 달랐던 기존 보험료 벤치마크 테이블. cleanup migration으로 제거했다. |
| `policy_change_notes` | removed | 제거된 구 분석 API 전용 제도 변경 메모. cleanup migration으로 제거했다. |

상태 표는 마이그레이션 적용 이력이 아니라 현재 사용 계약을 기록한다. migration은 이미 적용된 이력이므로 삭제하거나 재작성하지 않는다. 잘못된 정의나 중복은 새 migration으로 정리하고, 전환 기간에는 읽기 경로와 영향 범위를 명시한다.

## 새 환경 초기 데이터

`coverly.reference_data` migration은 테이블 구조와 이력을 관리한다. `claim_channels`, `disclosure_links`의 실제 payload는 Supabase 운영 데이터로 관리하며, 새 로컬·스테이징 환경도 승인된 DB 작업이나 새 migration으로 같은 row를 준비해야 한다. 서버 repo의 seed 스크립트나 bundled JSON으로 운영 데이터를 복제하지 않는다.

## 운영 규칙

- 참조 사실에는 출처와 기준일을 저장하고 응답 근거에 연결한다.
- RAG 검색 결과가 없거나 근거가 부족하면 서버는 확인 불가로 degrade한다.
- Supabase 소유 참조 데이터에는 서버 bundled fallback을 두지 않는다.
- `claim_channels`, `disclosure_links`가 없거나 읽히지 않으면 전체 분석을 실패시킨다.
- 참조 데이터 스키마 변경은 새 migration과 검증 코드를 함께 추가한다.
