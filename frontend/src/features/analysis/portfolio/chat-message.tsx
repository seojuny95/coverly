"use client";

import {
  type ComponentPropsWithoutRef,
  memo,
  useEffect,
  useState,
} from "react";
import ReactMarkdown, { type Components } from "react-markdown";

import { safeHref } from "./safe-href";

const THINKING_PHRASES = [
  "증권을 읽는 중",
  "근거를 확인하는 중",
  "답변을 정리하는 중",
];

function ThinkingIndicator() {
  const [phraseIndex, setPhraseIndex] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setPhraseIndex((index) => (index + 1) % THINKING_PHRASES.length);
    }, 1600);
    return () => clearInterval(timer);
  }, []);

  return (
    <span
      role="status"
      aria-label="답변 준비 중"
      className="flex items-center gap-2 text-zinc-500"
    >
      <span>{THINKING_PHRASES[phraseIndex]}</span>
      <span className="flex gap-1" aria-hidden>
        {[0, 150, 300].map((delay) => (
          <span
            key={delay}
            className="inline-block h-1.5 w-1.5 animate-bounce rounded-full bg-zinc-400"
            style={{ animationDelay: `${delay}ms` }}
          />
        ))}
      </span>
    </span>
  );
}

const markdownComponents: Components = {
  p: (props) => <p className="mb-2 last:mb-0" {...props} />,
  strong: (props) => <strong className="font-semibold" {...props} />,
  ul: (props) => (
    <ul className="mb-2 list-disc space-y-1 pl-5 last:mb-0" {...props} />
  ),
  ol: (props) => (
    <ol className="mb-2 list-decimal space-y-1 pl-5 last:mb-0" {...props} />
  ),
  li: (props) => <li className="pl-0.5" {...props} />,
  a: ({ href, ...props }: ComponentPropsWithoutRef<"a">) => (
    <a
      href={safeHref(href)}
      target="_blank"
      rel="noopener noreferrer"
      className="text-blue-600 underline underline-offset-2 hover:text-blue-700"
      {...props}
    />
  ),
};

export type ChatMessageData = {
  id: number;
  role: "user" | "assistant";
  text: string;
};

function ChatMessageComponent({ message }: { message: ChatMessageData }) {
  const isUser = message.role === "user";
  return (
    <article
      className={`max-w-[90%] rounded-2xl px-4 py-3 text-sm leading-6 ${
        isUser
          ? "ml-auto bg-blue-600 text-white"
          : "border border-zinc-200 bg-white text-zinc-700"
      }`}
    >
      {isUser ? (
        <p className="whitespace-pre-line">{message.text}</p>
      ) : message.text.trim() === "" ? (
        <ThinkingIndicator />
      ) : (
        <div className="[word-break:break-word]">
          <ReactMarkdown components={markdownComponents}>
            {message.text}
          </ReactMarkdown>
        </div>
      )}
    </article>
  );
}

// Memoized so a streaming answer (which rebuilds the messages array on each
// token) only re-renders the message whose text actually changed, not every
// prior ChatMessage (each of which runs ReactMarkdown).
export const ChatMessage = memo(ChatMessageComponent);
