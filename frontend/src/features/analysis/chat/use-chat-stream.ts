"use client";

import { useEffect, useRef, useState } from "react";
import { streamPortfolioQuestion } from "./api";
import type { ChatHistoryItem } from "../coverage/types";

type ChatStreamRequest = {
  question: string;
  history: ChatHistoryItem[];
  assistantId: number;
};

const DELTA_FLUSH_INTERVAL_MS = 50;

export function useChatStream({
  portfolioSessionToken,
  onDelta,
  onTurnsChanged,
  onCompleted,
  onFailed,
}: {
  portfolioSessionToken: string;
  onDelta: (assistantId: number, delta: string) => void;
  onTurnsChanged: (turnsRemaining: number) => void;
  onCompleted: () => void;
  onFailed: (error: unknown, assistantId: number) => void;
}) {
  const [streaming, setStreaming] = useState(false);
  const streamingRef = useRef(false);
  const activeRequest = useRef<AbortController | null>(null);
  const cancelActiveBatch = useRef<(() => void) | null>(null);

  useEffect(() => {
    return () => {
      cancelActiveBatch.current?.();
      activeRequest.current?.abort();
    };
  }, []);

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
    const deltaBatch = createDeltaBatch({
      assistantId: request.assistantId,
      onDelta,
    });
    cancelActiveBatch.current = deltaBatch.cancel;

    try {
      await streamPortfolioQuestion(
        request.question,
        request.history,
        {
          onDelta: deltaBatch.enqueue,
          onMeta: (meta) => onTurnsChanged(meta.turns_remaining),
          onEnd: () => {
            deltaBatch.flush();
            onCompleted();
          },
        },
        portfolioSessionToken,
        controller.signal,
      );
    } catch (error) {
      deltaBatch.cancel();
      if (!controller.signal.aborted) {
        onFailed(error, request.assistantId);
      }
    } finally {
      if (activeRequest.current === controller) {
        deltaBatch.cancel();
        cancelActiveBatch.current = null;
        activeRequest.current = null;
        streamingRef.current = false;
        setStreaming(false);
      }
    }
  }

  return { streaming, startStream };
}

function createDeltaBatch({
  assistantId,
  onDelta,
}: {
  assistantId: number;
  onDelta: (assistantId: number, delta: string) => void;
}) {
  let pendingDelta = "";
  let flushTimer: number | undefined;

  const flush = () => {
    if (flushTimer !== undefined) {
      window.clearTimeout(flushTimer);
      flushTimer = undefined;
    }
    if (!pendingDelta) return;

    const delta = pendingDelta;
    pendingDelta = "";
    onDelta(assistantId, delta);
  };

  const enqueue = (delta: string) => {
    pendingDelta += delta;
    if (flushTimer !== undefined) return;

    flushTimer = window.setTimeout(flush, DELTA_FLUSH_INTERVAL_MS);
  };

  const cancel = () => {
    if (flushTimer !== undefined) window.clearTimeout(flushTimer);
    flushTimer = undefined;
    pendingDelta = "";
  };

  return { cancel, enqueue, flush };
}
