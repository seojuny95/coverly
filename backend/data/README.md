# RAG 데이터

이 디렉터리는 Coverly RAG에 쓰는 공식 원문을 둔다.

공식문서 RAG corpus는 `official-sources/` 아래에서 관리한다. `official-sources/registry.json`은
각 원문의 ID, 제목, 출처, 문서 타입, 로컬 파일 경로, 해시, RAG 사용 여부를 담는 manifest다.
인덱싱 코드는 이 registry만 보고 어떤 파일을 읽을지 결정하며, `local_path`는
`official-sources/` 기준 상대경로다.

현재 범위는 다음으로 제한한다.

- 표준약관: `official-sources/standard-clauses/`
- 소비자 안내자료: `official-sources/consumer-guides/`
- 핵심 법령 XML 스냅샷: `official-sources/laws/`

사용자 업로드 증권 원문은 이 디렉터리에 저장하지 않는다. 구조화 증권과 Policy RAG 청크는 만료되는 포트폴리오 세션 범위에서만 사용한다. 사용자가 세션을 삭제하면 연결 데이터를 정리하고, 만료 세션의 물리 정리는 새 세션 생성 시 수행한다. 저장 대상·삭제 경로·토큰 경계의 기준은 [../REFERENCE_DATA.md](../REFERENCE_DATA.md)의 포트폴리오 세션 운영 규칙을 따른다.
