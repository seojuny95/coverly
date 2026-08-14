"use client";

import { useCallback, useState } from "react";
import { useDialogA11y } from "./use-dialog-a11y";
import { ChatLauncher } from "./launcher";
import { ChatComposer } from "./composer";
import { ChatConversationLog } from "./conversation-log";
import { useInsuranceChat } from "./use-chat";

export function InsuranceChatbot({
  portfolioSessionToken,
  sessionExpired = false,
  turnsRemaining: initialTurnsRemaining,
  mode = "floating",
  initiallyOpen = false,
  onExpand,
  onSessionExpired,
}: {
  portfolioSessionToken: string;
  sessionExpired?: boolean;
  turnsRemaining: number;
  mode?: "floating" | "full";
  initiallyOpen?: boolean;
  onExpand?: () => void;
  onSessionExpired?: () => void;
}) {
  const [open, setOpen] = useState(initiallyOpen);
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
    onSessionExpired,
  });

  // autoFocus: false — this dialog already focuses the question input itself
  // (via the hook), which is a better initial target than the "닫기" button.
  const dialogRef = useDialogA11y<HTMLElement>({
    open: isFloating && open,
    onClose: closeChatbot,
    autoFocus: false,
    trapFocus: false,
  });

  if (isFloating && !open) {
    return (
      <ChatLauncher disabled={sessionExpired} onOpen={() => setOpen(true)} />
    );
  }

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

      <ChatConversationLog messages={messages} endRef={endRef} />
      <ChatComposer
        question={question}
        suggestions={suggestions}
        streaming={streaming}
        sessionExpired={sessionExpired}
        turnsRemaining={turnsRemaining}
        inputRef={inputRef}
        onQuestionChange={setQuestion}
        onSuggestion={(suggestion) => void sendQuestion(suggestion)}
        onSubmit={submit}
      />
    </>
  );

  if (!isFloating) {
    return (
      <div className="mb-4 flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-[8px_8px_0_#eef2ff] sm:mb-6">
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
