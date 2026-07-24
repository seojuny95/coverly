"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import type { ChatMessageData } from "./chat-message";
import { streamPortfolioQuestion, type ChatHistoryItem } from "./api";
import { isExpiredSessionError } from "./session-errors";
import {
  reportClientOperationFailure,
  userMessageForError,
} from "@/shared/api/errors";

// Kept in step with the suggestion_* cases in backend/evals/qa/dataset.json:
// a question the product offers first has to be one it can actually answer.
const INITIAL_SUGGESTIONS = [
  "겹치는 보장이 있는지 봐줄래요?",
  "내 보험에서 비어 있는 보장이 있나요?",
  "실손의료비는 어디로 청구해요?",
];

export function useInsuranceChat({
  portfolioSessionToken,
  sessionExpired,
  isChatVisible,
  initialTurnsRemaining,
  onSessionExpired,
}: {
  portfolioSessionToken: string;
  sessionExpired: boolean;
  isChatVisible: boolean;
  initialTurnsRemaining: number;
  onSessionExpired?: () => void;
}) {
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<ChatMessageData[]>([
    {
      id: 0,
      role: "assistant",
      text: "안녕하세요. 올려주신 보험을 같이 살펴볼게요. 궁금한 건 편하게 말씀해 주세요.",
    },
  ]);
  const [suggestions, setSuggestions] = useState(INITIAL_SUGGESTIONS);
  const [streaming, setStreaming] = useState(false);
  const [turnsRemaining, setTurnsRemaining] = useState(initialTurnsRemaining);
  const streamingRef = useRef(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const nextMessageId = useRef(1);
  const activeRequest = useRef<AbortController | null>(null);

  useEffect(() => {
    if (isChatVisible) inputRef.current?.focus();
  }, [isChatVisible]);

  useEffect(() => {
    if (typeof endRef.current?.scrollIntoView === "function") {
      endRef.current.scrollIntoView({ block: "nearest" });
    }
  }, [streaming, messages]);

  useEffect(() => {
    if (!isChatVisible) activeRequest.current?.abort();
  }, [isChatVisible]);

  useEffect(
    () => () => {
      activeRequest.current?.abort();
    },
    [],
  );

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

  async function sendQuestion(rawQuestion: string) {
    const text = rawQuestion.trim();
    if (!text || streamingRef.current || sessionExpired || turnsRemaining <= 0)
      return;
    streamingRef.current = true;
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
    activeRequest.current?.abort();
    const request = new AbortController();
    activeRequest.current = request;
    setStreaming(true);
    try {
      await streamPortfolioQuestion(
        text,
        history,
        {
          onDelta: (delta) => {
            updateMessage(assistantId, (message) => ({
              ...message,
              text: message.text + delta,
            }));
          },
          onMeta: (meta) => setTurnsRemaining(meta.turns_remaining),
          onEnd: () => setSuggestions(INITIAL_SUGGESTIONS),
        },
        portfolioSessionToken,
        request.signal,
      );
    } catch (error) {
      if (request.signal.aborted) {
        updateMessage(assistantId, (message) => ({
          ...message,
          text: "질문을 중단했어요.",
        }));
        setSuggestions(INITIAL_SUGGESTIONS);
        return;
      }
      // Another tab may have spent the last turn, so trust the server over local state.
      const outOfTurns = isTurnLimitError(error);
      const expiredSession = isExpiredSessionError(error);
      reportClientOperationFailure("qa_stream", error);
      if (outOfTurns) setTurnsRemaining(0);
      if (expiredSession) onSessionExpired?.();
      updateMessage(assistantId, (message) => ({
        ...message,
        text: chatErrorMessage({
          error,
          outOfTurns,
          expiredSession,
        }),
      }));
      setSuggestions(INITIAL_SUGGESTIONS);
    } finally {
      if (activeRequest.current === request) {
        activeRequest.current = null;
        streamingRef.current = false;
        setStreaming(false);
      }
    }
  }

  return {
    question,
    setQuestion,
    messages,
    suggestions,
    streaming,
    turnsRemaining,
    inputRef,
    endRef,
    submit,
    sendQuestion,
  };
}

function isTurnLimitError(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    "code" in error &&
    (error as { code?: unknown }).code === "COUNSEL_TURN_LIMIT_REACHED"
  );
}

function chatErrorMessage({
  error,
  outOfTurns,
  expiredSession,
}: {
  error: unknown;
  outOfTurns: boolean;
  expiredSession: boolean;
}) {
  if (expiredSession) {
    return "분석 세션이 만료됐어요. 다시 분석하려면 보험증권을 다시 올려주세요.";
  }
  if (outOfTurns) return "이 분석에서 할 수 있는 질문을 모두 사용했어요.";
  return userMessageForError(
    error,
    "답을 가져오지 못했어요. 대화 내용은 그대로 있으니 잠시 후 다시 질문해주세요.",
  );
}
