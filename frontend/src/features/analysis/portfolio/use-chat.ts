"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import type { AnalyzedInsurance } from "../store";
import type { ChatMessageData } from "./chat-message";
import {
  streamPortfolioQuestion,
  type ChatHistoryItem,
  type QaStreamEnd,
} from "./api";

const INITIAL_SUGGESTIONS = [
  "내 보험에서 확인된 강점은 뭐예요?",
  "겹치는 보장이 있는지 봐줄래요?",
  "확인 가능한 보장금 합계는 얼마예요?",
];

export function useQaChat({
  documents,
  portfolioSessionToken,
  sessionExpired,
  isChatVisible,
}: {
  documents: AnalyzedInsurance[];
  portfolioSessionToken: string;
  sessionExpired: boolean;
  isChatVisible: boolean;
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
      limitations: end.limitations,
      claimChannels: end.claim_channels,
    }));
    setSuggestions(
      end.suggestions?.length ? end.suggestions : INITIAL_SUGGESTIONS,
    );
  }

  async function sendQuestion(rawQuestion: string) {
    const text = rawQuestion.trim();
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
      await streamPortfolioQuestion(
        text,
        documents,
        history,
        {
          onProgress: (progress) => {
            updateMessage(assistantId, (message) => ({
              ...message,
              progress: message.text.trim() ? message.progress : progress.text,
            }));
          },
          onDelta: (delta) => {
            updateMessage(assistantId, (message) => ({
              ...message,
              progress: undefined,
              text: message.text + delta,
            }));
          },
          onEnd: (end) => finalizeAnswer(assistantId, end),
        },
        portfolioSessionToken,
      );
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

  return {
    question,
    setQuestion,
    messages,
    suggestions,
    streaming,
    inputRef,
    endRef,
    submit,
    sendQuestion,
  };
}
