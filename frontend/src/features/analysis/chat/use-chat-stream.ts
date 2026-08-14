"use client";

import { useEffect, useRef, useState } from "react";
import { streamPortfolioQuestion } from "./api";
import type { ChatHistoryItem } from "../coverage/types";

type ChatStreamRequest = {
  question: string;
  history: ChatHistoryItem[];
  assistantId: number;
  turnsBeforeQuestion: number;
};

export function useChatStream({
  portfolioSessionToken,
  isChatVisible,
  onDelta,
  onTurnsChanged,
  onCompleted,
  onCancelled,
  onFailed,
}: {
  portfolioSessionToken: string;
  isChatVisible: boolean;
  onDelta: (assistantId: number, delta: string) => void;
  onTurnsChanged: (turnsRemaining: number) => void;
  onCompleted: () => void;
  onCancelled: (assistantId: number, turnsBeforeQuestion: number) => void;
  onFailed: (error: unknown, assistantId: number) => void;
}) {
  const [streaming, setStreaming] = useState(false);
  const streamingRef = useRef(false);
  const activeRequest = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!isChatVisible) activeRequest.current?.abort();
  }, [isChatVisible]);

  useEffect(
    () => () => {
      activeRequest.current?.abort();
    },
    [],
  );

  function startStream(
    request: ChatStreamRequest,
    onStarted: () => void,
  ): boolean {
    if (streamingRef.current) return false;

    streamingRef.current = true;
    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;
    setStreaming(true);
    onStarted();

    void runStream(request, controller);
    return true;
  }

  async function runStream(
    request: ChatStreamRequest,
    controller: AbortController,
  ) {
    try {
      await streamPortfolioQuestion(
        request.question,
        request.history,
        {
          onDelta: (delta) => onDelta(request.assistantId, delta),
          onMeta: (meta) => onTurnsChanged(meta.turns_remaining),
          onEnd: onCompleted,
        },
        portfolioSessionToken,
        controller.signal,
      );
    } catch (error) {
      if (controller.signal.aborted) {
        onCancelled(request.assistantId, request.turnsBeforeQuestion);
      } else {
        onFailed(error, request.assistantId);
      }
    } finally {
      if (activeRequest.current === controller) {
        activeRequest.current = null;
        streamingRef.current = false;
        setStreaming(false);
      }
    }
  }

  return { streaming, startStream };
}
