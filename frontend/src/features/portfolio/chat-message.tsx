"use client";

import { type ComponentPropsWithoutRef, useEffect, useState } from "react";
import ReactMarkdown, { type Components } from "react-markdown";

import type { ClaimChannelBlock } from "./portfolio-api";
import { safeHref } from "./safe-href";

type ChatSource = { label: string };

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
  sources?: ChatSource[];
  limitations?: string[];
  claimChannels?: ClaimChannelBlock | null;
};

export function ChatMessage({ message }: { message: ChatMessageData }) {
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
      {message.claimChannels ? (
        <ClaimChannels block={message.claimChannels} />
      ) : null}
      {message.sources?.length ? (
        <div className="mt-3 border-t border-zinc-100 pt-3">
          <p className="text-[11px] font-semibold text-zinc-500">확인한 근거</p>
          <ul className="mt-1 space-y-1 text-xs text-zinc-500">
            {message.sources.map((source, index) => (
              <li key={`${source.label}-${index}`}>{source.label}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {message.limitations?.length ? (
        <div className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-900">
          {message.limitations.map((item, index) => (
            <p key={`${item}-${index}`}>{item}</p>
          ))}
        </div>
      ) : null}
    </article>
  );
}

function ChannelLinks({
  links,
}: {
  links: ClaimChannelBlock["insurers"][number]["links"];
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
        {block.insurers.map((insurer) => (
          <li key={insurer.name}>
            <span className="font-medium text-zinc-700">{insurer.name}</span>
            {insurer.customer_center ? (
              <span className="ml-1">고객센터 {insurer.customer_center}</span>
            ) : null}
            <ChannelLinks links={insurer.links} />
          </li>
        ))}
        {block.indemnity ? (
          <li>
            <span className="font-medium text-zinc-700">
              {block.indemnity.name}
            </span>
            {block.indemnity.call_center ? (
              <span className="ml-1">콜센터 {block.indemnity.call_center}</span>
            ) : null}
            <ChannelLinks links={block.indemnity.links} />
          </li>
        ) : null}
      </ul>
    </div>
  );
}
