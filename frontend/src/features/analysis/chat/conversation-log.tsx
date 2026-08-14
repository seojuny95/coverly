import type { RefObject } from "react";
import { ChatMessage, type ChatMessageData } from "./message";

export function ChatConversationLog({
  messages,
  endRef,
}: {
  messages: ChatMessageData[];
  endRef: RefObject<HTMLDivElement | null>;
}) {
  return (
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
  );
}
