-- Counsel turns are capped per portfolio session. The counter lives on the
-- session row so adding more policy documents never resets or raises it: an
-- upload touches policy_documents and the session version, not this column.
alter table private.portfolio_sessions
  add column counsel_turns_used bigint not null default 0;

alter table private.portfolio_sessions
  add constraint portfolio_session_counsel_turns_not_negative
  check (counsel_turns_used >= 0);

comment on column private.portfolio_sessions.counsel_turns_used is
  '이 세션에서 사용한 상담 질문 수. 증권을 추가해도 초기화되지 않는다.';
