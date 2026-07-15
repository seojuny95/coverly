"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import type { AnalyzedInsurance } from "../insurance-analysis/insurance-analysis-store";
import { useDialogA11y } from "../insurance-analysis/use-dialog-a11y";
import { primaryButtonClassName } from "../../components/coverly-brand";
import { ChatMessage, type ChatMessageData } from "./chat-message";
import {
  streamPortfolioQuestion,
  type ChatHistoryItem,
  type QaStreamEnd,
} from "./portfolio-api";

const INITIAL_SUGGESTIONS = [
  "내 보험에서 확인된 강점은 뭐예요?",
  "겹치는 보장이 있는지 봐줄래요?",
  "확인 가능한 보장금 합계는 얼마예요?",
];

const INITIAL_ONLY_LIMITATIONS = [
  "보상 조건·면책·지급 가능성은 약관 근거 없이 판단하지 않습니다.",
  "실손형 담보는 가입금액 합계에 포함하지 않았습니다.",
  "지급유형 또는 금액이 확인되지 않은 담보는 합계에 포함하지 않았습니다.",
  "손해보험은 보장금 합계에 포함하지 않았어요.",
];

export function InsuranceChatbot({
  documents,
  sessionExpired = false,
  mode = "floating",
  onExpand,
}: {
  documents: AnalyzedInsurance[];
  sessionExpired?: boolean;
  mode?: "floating" | "full";
  onExpand?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<ChatMessageData[]>([
    {
      id: 0,
      role: "assistant",
      text: "궁금한 내용을 물어보세요. AI가 올린 보험증권에서 확인한 사실을 근거로 답할게요. Coverly AI는 보험을 팔지 않아요.",
      limitations: [
        "자동차보험과 약관이 필요한 보상 판단은 답변에서 제외해요.",
        ...INITIAL_ONLY_LIMITATIONS,
      ],
    },
  ]);
  const [suggestions, setSuggestions] = useState(INITIAL_SUGGESTIONS);
  const inputRef = useRef<HTMLInputElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const nextMessageId = useRef(1);

  const [streaming, setStreaming] = useState(false);
  const closeChatbot = useCallback(() => setOpen(false), []);
  const isFloating = mode === "floating";
  const isChatVisible = !isFloating || open;
  // autoFocus: false — this dialog already focuses the question input itself
  // (below), which is a better initial target than the "닫기" button.
  const dialogRef = useDialogA11y<HTMLElement>({
    open: isFloating && open,
    onClose: closeChatbot,
    autoFocus: false,
  });

  useEffect(() => {
    if (isChatVisible) inputRef.current?.focus();
  }, [isChatVisible]);

  useEffect(() => {
    if (typeof endRef.current?.scrollIntoView === "function") {
      endRef.current.scrollIntoView({ block: "nearest" });
    }
  }, [streaming, messages]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    await sendQuestion(question);
  }

  function updateMessage(
    id: number,
    change: (message: ChatMessageData) => ChatMessageData,
  ) {
    setMessages((current) =>
      current.map((message) => (message.id === id ? change(message) : message)),
    );
  }

  function finalizeAnswer(assistantId: number, end: QaStreamEnd) {
    const sources = end.citations
      .map((citation) => ({
        label: [citation.insurer, citation.product_name, citation.coverage_name]
          .filter(Boolean)
          .join(" · "),
      }))
      .filter((source) => source.label)
      .slice(0, 3);
    updateMessage(assistantId, (message) => ({
      ...message,
      sources,
      limitations: end.limitations.filter(
        (item) => !INITIAL_ONLY_LIMITATIONS.includes(item),
      ),
      claimChannels: end.claim_channels,
    }));
    setSuggestions(
      end.suggestions?.length ? end.suggestions : INITIAL_SUGGESTIONS,
    );
  }

  async function sendQuestion(rawQuestion: string) {
    const text = rawQuestion.trim().slice(0, 500);
    if (!text || streaming || sessionExpired) return;
    const userId = nextMessageId.current;
    const assistantId = userId + 1;
    nextMessageId.current += 2;
    const history: ChatHistoryItem[] = messages
      .filter((message) => message.id !== 0)
      .map((message) => ({ role: message.role, content: message.text }));
    setQuestion("");
    setSuggestions([]);
    setMessages((current) => [
      ...current,
      { id: userId, role: "user", text },
      { id: assistantId, role: "assistant", text: "" },
    ]);
    setStreaming(true);
    try {
      await streamPortfolioQuestion(text, documents, history, {
        onDelta: (delta) =>
          updateMessage(assistantId, (message) => ({
            ...message,
            text: message.text + delta,
          })),
        onEnd: (end) => finalizeAnswer(assistantId, end),
      });
    } catch {
      updateMessage(assistantId, (message) => ({
        ...message,
        text: "답을 가져오지 못했어요. 대화 내용은 그대로 있으니 잠시 후 다시 질문해주세요.",
      }));
      setSuggestions(INITIAL_SUGGESTIONS);
    } finally {
      setStreaming(false);
    }
  }

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
      <header className="flex items-center justify-between border-b border-zinc-100 px-5 py-4">
        <div>
          <h2
            className={isFloating ? "font-semibold" : "text-xl font-semibold"}
          >
            AI 보험 상담
          </h2>
          <p className="mt-1 text-xs text-zinc-500">
            증권 근거와 확인 한계를 함께 보여드려요
          </p>
        </div>
        {isFloating ? (
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
        ) : null}
      </header>

      <div
        aria-live="polite"
        className="flex-1 space-y-3 overflow-y-auto bg-zinc-50/60 p-4 sm:p-5"
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
        {suggestions.length ? (
          <div className="mb-3 flex gap-2 overflow-x-auto pb-1">
            {suggestions.map((suggestion) => (
              <button
                key={suggestion}
                type="button"
                disabled={streaming || sessionExpired}
                onClick={() => void sendQuestion(suggestion)}
                className="shrink-0 rounded-full border border-blue-200 bg-blue-50 px-3 py-2 text-xs font-medium text-blue-700 hover:bg-blue-100 disabled:opacity-50"
              >
                {suggestion}
              </button>
            ))}
          </div>
        ) : null}
        <form onSubmit={submit}>
          <label htmlFor="insurance-question" className="sr-only">
            보험 질문
          </label>
          <div className="flex gap-2">
            <input
              ref={inputRef}
              id="insurance-question"
              maxLength={500}
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              disabled={sessionExpired}
              autoComplete="off"
              autoCorrect="off"
              spellCheck={false}
              placeholder="예: 겹치는 보장이 있나요?"
              className="min-w-0 flex-1 rounded-xl border border-zinc-300 px-4 py-3 text-sm outline-none focus:border-blue-600 disabled:bg-zinc-100 disabled:text-zinc-500"
            />
            <button
              type="submit"
              disabled={!question.trim() || streaming || sessionExpired}
              className={primaryButtonClassName}
            >
              질문하기
            </button>
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
        className="mb-4 flex min-h-[28rem] flex-1 flex-col overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-[8px_8px_0_#eef2ff] sm:mb-6"
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
      className="fixed inset-0 z-40 flex flex-col overflow-hidden bg-white shadow-2xl sm:inset-x-auto sm:top-auto sm:right-8 sm:bottom-8 sm:h-[min(78vh,46rem)] sm:w-[min(32rem,calc(100vw-4rem))] sm:rounded-2xl sm:border sm:border-zinc-200"
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
