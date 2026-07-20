"use client";

import { useCallback, useState } from "react";
import { useDialogA11y } from "../use-dialog-a11y";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { ChatMessage } from "./chat-message";
import { useInsuranceChat } from "./use-chat";

export function InsuranceChatbot({
  portfolioSessionToken,
  sessionExpired = false,
  turnsRemaining: initialTurnsRemaining,
  mode = "floating",
  onExpand,
}: {
  portfolioSessionToken: string;
  sessionExpired?: boolean;
  turnsRemaining: number;
  mode?: "floating" | "full";
  onExpand?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const closeChatbot = useCallback(() => setOpen(false), []);
  const isFloating = mode === "floating";
  const isChatVisible = !isFloating || open;

  const {
    question,
    setQuestion,
    messages,
    suggestions,
    streaming,
    inputRef,
    turnsRemaining,
    endRef,
    submit,
    sendQuestion,
  } = useInsuranceChat({
    portfolioSessionToken,
    sessionExpired,
    isChatVisible,
    initialTurnsRemaining,
  });

  // autoFocus: false — this dialog already focuses the question input itself
  // (via the hook), which is a better initial target than the "닫기" button.
  const dialogRef = useDialogA11y<HTMLElement>({
    open: isFloating && open,
    onClose: closeChatbot,
    autoFocus: false,
  });

  if (isFloating && !open)
    return (
      <button
        type="button"
        onClick={() => {
          if (!sessionExpired) setOpen(true);
        }}
        disabled={sessionExpired}
        className="fixed right-5 bottom-5 z-40 min-h-14 rounded-2xl bg-blue-600 px-6 py-4 text-base font-semibold text-white shadow-xl disabled:cursor-not-allowed disabled:bg-zinc-300 sm:right-8 sm:bottom-8"
      >
        AI 상담사에게 질문하기
      </button>
    );

  const chat = (
    <>
      {isFloating ? (
        <header className="flex items-center justify-between border-b border-zinc-100 px-5 py-4">
          <div>
            <h2 className="font-semibold">AI 보험 상담</h2>
            <p className="mt-1 text-xs text-zinc-500">
              올려주신 증권을 바탕으로 함께 살펴봐요
            </p>
          </div>
          <div className="flex items-center gap-1">
            {onExpand ? (
              <button
                type="button"
                onClick={onExpand}
                aria-label="AI 보험 상담 탭에서 크게 보기"
                className="rounded-lg p-2 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-950 focus-visible:outline-2 focus-visible:outline-blue-600"
              >
                <ExpandIcon />
              </button>
            ) : null}
            <button
              type="button"
              onClick={closeChatbot}
              className="rounded-lg px-3 py-2 text-sm hover:bg-zinc-100 focus-visible:outline-2 focus-visible:outline-blue-600"
            >
              닫기
            </button>
          </div>
        </header>
      ) : null}

      <div
        role="log"
        aria-label="보험 상담 대화"
        aria-live="polite"
        className="min-h-0 flex-1 space-y-3 overflow-y-auto bg-zinc-50/60 p-4 sm:p-5"
      >
        {messages.map((message) => (
          <ChatMessage key={message.id} message={message} />
        ))}
        <div ref={endRef} />
      </div>

      <div className="border-t border-zinc-100 bg-white p-4">
        {sessionExpired ? (
          <div
            role="status"
            className="mb-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-950"
          >
            분석 세션이 만료됐어요. 다시 분석하려면 보험증권을 다시 올려주세요.
          </div>
        ) : null}
        {!sessionExpired && turnsRemaining <= 0 ? (
          <div
            role="status"
            className="motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-2 mb-3 flex items-start gap-3 rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm leading-6 text-blue-950 motion-safe:duration-300"
          >
            <span aria-hidden className="mt-0.5 text-base">
              💬
            </span>
            <span>
              이 분석에서 할 수 있는 질문을 모두 사용했어요. 보험증권을 다시
              올려 새로 분석하면 이어서 물어볼 수 있어요.
            </span>
          </div>
        ) : null}
        {suggestions.length ? (
          <div className="mb-3 flex gap-2 overflow-x-auto pb-1">
            {suggestions.map((suggestion) => (
              <button
                key={suggestion}
                type="button"
                disabled={streaming || sessionExpired || turnsRemaining <= 0}
                onClick={() => void sendQuestion(suggestion)}
                className="shrink-0 rounded-full border border-blue-200 bg-blue-50 px-3 py-2 text-xs font-medium text-blue-700 hover:bg-blue-100 disabled:opacity-50"
              >
                {suggestion}
              </button>
            ))}
          </div>
        ) : null}
        <form onSubmit={submit}>
          <div className="mb-2 flex items-baseline justify-between gap-2">
            <label htmlFor="insurance-question" className="sr-only">
              보험 질문
            </label>
            <p
              aria-live="polite"
              className={`ml-auto text-xs tabular-nums transition-colors ${
                turnsRemaining <= 0
                  ? "text-zinc-400"
                  : turnsRemaining <= 3
                    ? "font-medium text-amber-700"
                    : "text-zinc-500"
              }`}
            >
              질문 {turnsRemaining}번 남음
            </p>
          </div>
          <div className="flex gap-2">
            <Input
              ref={inputRef}
              id="insurance-question"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              disabled={sessionExpired || turnsRemaining <= 0}
              autoComplete="off"
              autoCorrect="off"
              spellCheck={false}
              placeholder={
                turnsRemaining <= 0
                  ? "질문 횟수를 모두 사용했어요"
                  : "예: 겹치는 보장이 있나요?"
              }
              className="h-auto min-w-0 flex-1 rounded-xl border border-zinc-300 px-4 py-3 text-sm outline-none focus:border-blue-600 focus-visible:ring-0 disabled:bg-zinc-100 disabled:text-zinc-500"
            />
            <Button
              type="submit"
              disabled={
                !question.trim() ||
                streaming ||
                sessionExpired ||
                turnsRemaining <= 0
              }
            >
              질문하기
            </Button>
          </div>
        </form>
      </div>
    </>
  );

  if (!isFloating) {
    return (
      <div
        id="chat-tabpanel"
        role="tabpanel"
        aria-labelledby="chat-tab"
        tabIndex={0}
        className="mb-4 flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-[8px_8px_0_#eef2ff] sm:mb-6"
      >
        {chat}
      </div>
    );
  }

  return (
    <aside
      ref={dialogRef}
      role="dialog"
      aria-label="내 보험 질문"
      aria-modal="false"
      tabIndex={-1}
      className="animate-enter fixed inset-0 z-40 flex flex-col overflow-hidden bg-white shadow-2xl sm:inset-x-auto sm:top-auto sm:right-8 sm:bottom-8 sm:h-[min(78vh,46rem)] sm:w-[min(32rem,calc(100vw-4rem))] sm:rounded-2xl sm:border sm:border-zinc-200"
    >
      {chat}
    </aside>
  );
}

function ExpandIcon() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      className="size-5"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M8 3H3v5" />
      <path d="m3 3 6 6" />
      <path d="M16 3h5v5" />
      <path d="m21 3-6 6" />
      <path d="M8 21H3v-5" />
      <path d="m3 21 6-6" />
      <path d="M16 21h5v-5" />
      <path d="m21 21-6-6" />
    </svg>
  );
}
