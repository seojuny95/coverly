# 데이터베이스와 참조 데이터

Coverly는 **Supabase를 데이터베이스로 사용**합니다. 이 문서는 새 개발 환경을 준비하고, 코드와 데이터의 책임을 구분하기 위한 안내입니다.

## 새 환경 준비

pgvector를 활성화한 새 Supabase 프로젝트를 만든 뒤 프로젝트 루트에서 실행합니다.

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/bootstrap.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/seed.sql
```

- `bootstrap.sql`은 현재 서버가 요구하는 테이블과 보안 설정을 생성합니다.
- `seed.sql`은 로컬·포트폴리오 기능 확인에 필요한 샘플 참조 데이터를 추가합니다.
- 운영 데이터를 복사하지 않으며, 기존 데이터가 있으면 덮어쓰지 않습니다.

공식 자료 RAG는 별도로 인덱싱합니다.

```bash
cd backend
uv run python -m app.rag.official.indexing
```

## SQL 파일의 역할

| 경로 | 역할 |
| --- | --- |
| `supabase/bootstrap.sql` | 새 프로젝트에 **현재 최종 스키마**를 생성 |
| `supabase/migrations/` | 기존 운영 DB에 적용된 **변경 이력**을 보존 |
| `supabase/seed.sql` | 로컬 실행용 **샘플 참조 데이터**를 추가 |

새 환경에서는 과거 migration을 처음부터 반복 실행하지 않습니다. Supabase는 각 환경에 적용한 migration 버전을 별도로 기록하므로, 기존 파일을 삭제하거나 수정하면 저장소와 원격 이력이 어긋날 수 있습니다.

## 데이터의 책임

| 위치 | 관리하는 내용 |
| --- | --- |
| 서버 코드 | PDF 파싱, 담보 분류·매칭, 합계 계산, grounding과 실패 처리 |
| `app/modules/portfolio/sample` | 포트폴리오 데모용 비식별 샘플 fixture와 세션 생성 로직 |
| `reference` 스키마 | 출처나 기준일에 따라 바뀔 수 있는 보험 참조 데이터 |
| `private` 스키마 | 만료되는 포트폴리오 세션, PII를 최소화한 증권 데이터, 세션별 분석 캐시 |
| RAG 테이블 | 공식 자료와 업로드한 증권 원문의 검색용 청크 |

서버는 다음 참조 데이터가 없거나 형식이 잘못되면 분석을 중단합니다. 오래된 내장 데이터로 조용히 대체하지 않습니다.

- `claim_channels`
- `death_benefit_guides`
- `disclosure_links`
- `essential_coverage_guides`
- `insurer_catalog`

## 운영 원칙

- 변경 가능한 참조 사실은 출처와 기준일을 함께 저장합니다.
- 기존 migration은 삭제하거나 수정하지 않고, 스키마 변경은 새 migration으로 추가합니다.
- seed에는 실제 고객 정보나 운영 데이터를 넣지 않습니다.
- 샘플 포트폴리오는 실제 업로드와 별도 세션 종류로 저장하고, 증권 추가·삭제 같은 문서 변경은 허용하지 않습니다.
- 증권 데이터는 저장 전에 PII를 마스킹하고, 세션 만료 시 함께 삭제합니다.
- `reference`, `private`, 증권 RAG 테이블은 브라우저 역할에서 직접 접근할 수 없도록 RLS와 권한을 제한합니다.
- RAG 근거가 부족하면 추측하지 않고 확인할 수 없다고 응답합니다.
