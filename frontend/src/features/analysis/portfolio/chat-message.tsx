"use client";

import {
  type ComponentPropsWithoutRef,
  memo,
  useEffect,
  useState,
} from "react";
import ReactMarkdown, { type Components } from "react-markdown";

import { Alert, AlertDescription } from "@/shared/components/ui/alert";

import type { ClaimChannelBlock } from "./api";
import { safeHref } from "./safe-href";

type ChatSource = { label: string };

const THINKING_PHRASES = [
  "증권을 읽는 중",
  "근거를 확인하는 중",
  "답변을 정리하는 중",
];

function ThinkingIndicator({ progress }: { progress?: string }) {
  const [phraseIndex, setPhraseIndex] = useState(0);

  useEffect(() => {
    if (progress) return;
    const timer = setInterval(() => {
      setPhraseIndex((index) => (index + 1) % THINKING_PHRASES.length);
    }, 1600);
    return () => clearInterval(timer);
  }, [progress]);

  return (
    <span
      role="status"
      aria-label="답변 준비 중"
      className="flex items-center gap-2 text-zinc-500"
    >
      <span>{progress || THINKING_PHRASES[phraseIndex]}</span>
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
  progress?: string;
  sources?: ChatSource[];
  limitations?: string[];
  claimChannels?: ClaimChannelBlock | null;
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
        <ThinkingIndicator progress={message.progress} />
      ) : (
        <div className="[word-break:break-word]">
          <ReactMarkdown components={markdownComponents}>
            {message.text}
          </ReactMarkdown>
        </div>
      )}
      {message.claimChannels ? (
        <ClaimChannels block={message.claimChannels} />
      ) : null}
      {message.sources?.length ? (
        <details className="group mt-3 border-t border-zinc-100 pt-3">
          <summary className="cursor-pointer text-[11px] font-semibold text-zinc-500 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600">
            확인한 근거
          </summary>
          <ul className="mt-1 space-y-1 text-xs text-zinc-500">
            {message.sources.map((source, index) => (
              <li key={`${source.label}-${index}`}>{source.label}</li>
            ))}
          </ul>
        </details>
      ) : null}
      {message.limitations?.length ? (
        <details className="group mt-3 border-t border-zinc-100 pt-3">
          <summary className="cursor-pointer text-[11px] font-semibold text-zinc-500 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600">
            답변의 확인 범위
          </summary>
          <Alert
            variant="warning"
            role="note"
            className="mt-2 gap-0 border-transparent px-3 py-2 text-xs leading-5 text-amber-900"
          >
            <AlertDescription className="text-xs text-pretty text-amber-900 [&_p:not(:last-child)]:mb-0">
              {message.limitations.map((item, index) => (
                <p key={`${item}-${index}`}>{item}</p>
              ))}
            </AlertDescription>
          </Alert>
        </details>
      ) : null}
    </article>
  );
}

// Memoized so a streaming answer (which rebuilds the messages array on each
// token) only re-renders the message whose text actually changed, not every
// prior ChatMessage (each of which runs ReactMarkdown).
export const ChatMessage = memo(ChatMessageComponent);

function ChannelLinks({
  links,
}: {
  links: NonNullable<
    NonNullable<ClaimChannelBlock["insurers"]>[number]["links"]
  >;
}) {
  if (!links.length) return null;
  return (
    <span className="ml-1 inline-flex flex-wrap gap-x-2">
      {links.map((link) => {
        const href = safeHref(link.url);
        if (!href) {
          return (
            <span key={`${link.label}-${link.url}`} className="text-zinc-500">
              {link.label}
            </span>
          );
        }

        return (
          <a
            key={`${link.label}-${link.url}`}
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-600 underline underline-offset-2 hover:text-blue-700"
          >
            {link.label}
          </a>
        );
      })}
    </span>
  );
}

function ClaimChannels({ block }: { block: ClaimChannelBlock }) {
  return (
    <div className="mt-3 space-y-2 border-t border-zinc-100 pt-3">
      <p className="text-[11px] font-semibold text-zinc-500">청구 방법 안내</p>
      <ul className="space-y-1.5 text-xs text-zinc-600">
        {(block.insurers ?? []).map((insurer) => (
          <li key={insurer.name}>
            <span className="font-medium text-zinc-700">{insurer.name}</span>
            {insurer.customer_center ? (
              <span className="ml-1">고객센터 {insurer.customer_center}</span>
            ) : null}
            <ChannelLinks links={insurer.links ?? []} />
          </li>
        ))}
        {block.medical_indemnity ? (
          <li>
            <span className="font-medium text-zinc-700">
              {block.medical_indemnity.name}
            </span>
            {block.medical_indemnity.call_center ? (
              <span className="ml-1">
                콜센터 {block.medical_indemnity.call_center}
              </span>
            ) : null}
            <ChannelLinks links={block.medical_indemnity.links ?? []} />
          </li>
        ) : null}
      </ul>
    </div>
  );
}
