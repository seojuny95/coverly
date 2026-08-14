"use client";

import { FormEvent, useEffect, useReducer, useRef } from "react";
import { isExpiredSessionError } from "../session/errors";
import {
  buildChatHistory,
  chatConversationReducer,
  createChatConversation,
} from "./conversation-state";
import { useChatStream } from "./use-chat-stream";
import {
  reportClientOperationFailure,
  userMessageForError,
} from "@/shared/api/errors";

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
  const [conversation, dispatch] = useReducer(
    chatConversationReducer,
    initialTurnsRemaining,
    createChatConversation,
  );
  const turnsRemaining = Math.min(
    conversation.turnsRemaining,
    initialTurnsRemaining,
  );
  const inputRef = useRef<HTMLInputElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const nextMessageId = useRef(1);

  const { streaming, startStream } = useChatStream({
    portfolioSessionToken,
    onDelta: (assistantId, delta) =>
      dispatch({ type: "answer_received", assistantId, delta }),
    onTurnsChanged: (nextTurnsRemaining) =>
      dispatch({
        type: "turns_updated",
        turnsRemaining: nextTurnsRemaining,
      }),
    onCompleted: () => dispatch({ type: "suggestions_restored" }),
    onFailed: handleStreamFailure,
  });

  useEffect(() => {
    if (isChatVisible) inputRef.current?.focus();
  }, [isChatVisible]);

  useEffect(() => {
    if (typeof endRef.current?.scrollIntoView === "function") {
      endRef.current.scrollIntoView({ block: "nearest" });
    }
  }, [streaming, conversation.messages]);

  function submit(event: FormEvent) {
    event.preventDefault();
    sendQuestion(conversation.question);
  }

  function sendQuestion(rawQuestion: string) {
    const text = rawQuestion.trim();
    if (!text || sessionExpired || turnsRemaining <= 0) return;

    const userId = nextMessageId.current;
    const assistantId = userId + 1;
    const history = buildChatHistory(conversation.messages);
    startStream(
      {
        question: text,
        history,
        assistantId,
      },
      () => {
        nextMessageId.current += 2;
        dispatch({
          type: "request_started",
          question: text,
          userId,
          assistantId,
        });
      },
    );
  }

  function handleStreamFailure(error: unknown, assistantId: number) {
    // Another tab may have spent the last turn, so trust the server over local state.
    const outOfTurns = isTurnLimitError(error);
    const expiredSession = isExpiredSessionError(error);
    const restoredTurns = restoredTurnsRemaining(error);
    reportClientOperationFailure("qa_stream", error);
    if (expiredSession) onSessionExpired?.();
    dispatch({
      type: "request_failed",
      assistantId,
      message: chatErrorMessage({ error, outOfTurns, expiredSession }),
      ...(outOfTurns
        ? { turnsRemaining: 0 }
        : restoredTurns === null
          ? {}
          : { turnsRemaining: restoredTurns }),
    });
  }

  return {
    question: conversation.question,
    setQuestion: (question: string) =>
      dispatch({ type: "question_changed", question }),
    messages: conversation.messages,
    suggestions: conversation.suggestions,
    streaming,
    turnsRemaining,
    inputRef,
    endRef,
    submit,
    sendQuestion,
  };
}

function restoredTurnsRemaining(error: unknown): number | null {
  if (
    typeof error !== "object" ||
    error === null ||
    !("turnsRemaining" in error)
  ) {
    return null;
  }
  const value = error.turnsRemaining;
  return typeof value === "number" && Number.isInteger(value) && value >= 0
    ? value
    : null;
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
