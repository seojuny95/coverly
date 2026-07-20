"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import type { ChatMessageData } from "./chat-message";
import { streamPortfolioQuestion, type ChatHistoryItem } from "./api";

const INITIAL_SUGGESTIONS = [
  "내 보험에서 확인된 강점은 뭐예요?",
  "겹치는 보장이 있는지 봐줄래요?",
  "확인 가능한 보장금 합계는 얼마예요?",
];

export function useInsuranceChat({
  portfolioSessionToken,
  sessionExpired,
  isChatVisible,
  initialTurnsRemaining,
}: {
  portfolioSessionToken: string;
  sessionExpired: boolean;
  isChatVisible: boolean;
  initialTurnsRemaining: number;
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
  const inputRef = useRef<HTMLInputElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const nextMessageId = useRef(1);

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

  async function sendQuestion(rawQuestion: string) {
    const text = rawQuestion.trim();
    if (!text || streaming || sessionExpired || turnsRemaining <= 0) return;
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
      );
    } catch (error) {
      // Another tab may have spent the last turn, so trust the server over local state.
      const outOfTurns = isTurnLimitError(error);
      if (outOfTurns) setTurnsRemaining(0);
      updateMessage(assistantId, (message) => ({
        ...message,
        text: outOfTurns
          ? "이 분석에서 할 수 있는 질문을 모두 사용했어요."
          : "답을 가져오지 못했어요. 대화 내용은 그대로 있으니 잠시 후 다시 질문해주세요.",
      }));
      setSuggestions(INITIAL_SUGGESTIONS);
    } finally {
      setStreaming(false);
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
