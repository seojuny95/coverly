import type { ChatMessageData } from "./message";
import type { ChatHistoryItem } from "../coverage/types";

// Keep these aligned with the backend suggestion evals: the product should
// only offer questions that the grounded QA flow is expected to answer.
const INITIAL_SUGGESTIONS = [
  "겹치는 보장이 있는지 봐줄래요?",
  "내 보험에서 비어 있는 보장이 있나요?",
  "실손의료비는 어디로 청구해요?",
];

export type ChatConversationState = {
  question: string;
  messages: ChatMessageData[];
  suggestions: string[];
  turnsRemaining: number;
};

export type ChatConversationAction =
  | { type: "question_changed"; question: string }
  | {
      type: "request_started";
      question: string;
      userId: number;
      assistantId: number;
    }
  | { type: "answer_received"; assistantId: number; delta: string }
  | { type: "turns_updated"; turnsRemaining: number }
  | { type: "suggestions_restored" }
  | {
      type: "request_cancelled";
      assistantId: number;
      turnsRemaining: number;
    }
  | {
      type: "request_failed";
      assistantId: number;
      message: string;
      turnsRemaining?: number;
    };

export function createChatConversation(
  turnsRemaining: number,
): ChatConversationState {
  return {
    question: "",
    messages: [
      {
        id: 0,
        role: "assistant",
        text: "안녕하세요. 올려주신 보험을 같이 살펴볼게요. 궁금한 건 편하게 말씀해 주세요.",
        kind: "answer",
      },
    ],
    suggestions: INITIAL_SUGGESTIONS,
    turnsRemaining,
  };
}

export function chatConversationReducer(
  state: ChatConversationState,
  action: ChatConversationAction,
): ChatConversationState {
  switch (action.type) {
    case "question_changed":
      return { ...state, question: action.question };
    case "request_started":
      return {
        ...state,
        question: "",
        suggestions: [],
        messages: [
          ...state.messages,
          {
            id: action.userId,
            role: "user",
            text: action.question,
            kind: "answer",
          },
          {
            id: action.assistantId,
            role: "assistant",
            text: "",
            kind: "answer",
          },
        ],
      };
    case "answer_received":
      return {
        ...state,
        messages: updateMessage(
          state.messages,
          action.assistantId,
          (message) => ({
            ...message,
            text: message.text + action.delta,
          }),
        ),
      };
    case "turns_updated":
      return { ...state, turnsRemaining: action.turnsRemaining };
    case "suggestions_restored":
      return { ...state, suggestions: INITIAL_SUGGESTIONS };
    case "request_cancelled":
      return {
        ...state,
        turnsRemaining: action.turnsRemaining,
        suggestions: INITIAL_SUGGESTIONS,
        messages: updateMessage(
          state.messages,
          action.assistantId,
          (message) => ({
            ...message,
            text: "질문을 중단했어요.",
            kind: "notice",
          }),
        ),
      };
    case "request_failed":
      return {
        ...state,
        ...(action.turnsRemaining === undefined
          ? {}
          : { turnsRemaining: action.turnsRemaining }),
        suggestions: INITIAL_SUGGESTIONS,
        messages: updateMessage(
          state.messages,
          action.assistantId,
          (message) => ({
            ...message,
            text: action.message,
            kind: "notice",
          }),
        ),
      };
  }
}

export function buildChatHistory(
  messages: ChatMessageData[],
): ChatHistoryItem[] {
  return messages
    .filter((message) => message.id !== 0 && message.kind === "answer")
    .map((message) => ({ role: message.role, content: message.text }));
}

function updateMessage(
  messages: ChatMessageData[],
  id: number,
  change: (message: ChatMessageData) => ChatMessageData,
): ChatMessageData[] {
  return messages.map((message) =>
    message.id === id ? change(message) : message,
  );
}
