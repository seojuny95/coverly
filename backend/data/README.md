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

사용자 업로드 증권 원문은 이 디렉터리에 저장하지 않는다. 업로드 증권 원문과 청크는 세션 안에서만 쓰고, 세션 종료 시 삭제하는 것을 원칙으로 한다.
