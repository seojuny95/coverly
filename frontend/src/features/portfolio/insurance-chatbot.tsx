"use client";

import { FormEvent, useState } from "react";
import type { AnalyzedInsurance } from "../insurance-analysis/insurance-analysis-store";
import { askPortfolioQuestion } from "./portfolio-api";

type Message = { id: number; role: "user" | "assistant"; text: string };

export function InsuranceChatbot({
  documents,
}: {
  documents: AnalyzedInsurance[];
}) {
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 0,
      role: "assistant",
      text: "업로드한 보험증권에서 확인한 내용을 바탕으로 답해드려요.",
    },
  ]);
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const text = question.trim();
    if (!text || loading) return;
    const id = Date.now();
    setQuestion("");
    setMessages((current) => [...current, { id, role: "user", text }]);
    setLoading(true);
    try {
      const answer = await askPortfolioQuestion(text, documents);
      const sourceLabels = answer.citations
        .map((citation) =>
          [citation.insurer, citation.product_name, citation.coverage_name]
            .filter(Boolean)
            .join(" · "),
        )
        .filter(Boolean);
      const details = [
        ...new Set(sourceLabels.map((label) => `근거: ${label}`)),
        ...answer.limitations,
      ];
      setMessages((current) => [
        ...current,
        {
          id: id + 1,
          role: "assistant",
          text: [answer.answer, ...details].join("\n"),
        },
      ]);
    } catch {
      setMessages((current) => [
        ...current,
        {
          id: id + 1,
          role: "assistant",
          text: "답을 가져오지 못했어요. 잠시 후 다시 질문해주세요.",
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  if (!open)
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="fixed right-5 bottom-5 z-40 rounded-2xl bg-blue-600 px-6 py-4 text-base font-semibold text-white shadow-xl sm:right-8 sm:bottom-8"
      >
        내 보험에 질문하기
      </button>
    );
  return (
    <aside
      role="dialog"
      aria-label="내 보험 질문"
      className="fixed inset-x-3 bottom-3 z-40 flex h-[min(82vh,42rem)] flex-col overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-2xl sm:inset-x-auto sm:right-8 sm:bottom-8 sm:h-[38rem] sm:w-[28rem]"
    >
      <header className="flex items-center justify-between border-b border-zinc-100 px-5 py-4">
        <div>
          <h2 className="font-semibold">내 보험에 질문하기</h2>
          <p className="mt-1 text-xs text-zinc-500">
            업로드한 증권을 기준으로 확인해요
          </p>
        </div>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="rounded-lg px-3 py-2 text-sm hover:bg-zinc-100"
        >
          닫기
        </button>
      </header>
      <div className="flex-1 space-y-3 overflow-y-auto bg-zinc-50/60 p-4">
        {messages.map((message) => (
          <p
            key={message.id}
            className={`max-w-[88%] rounded-2xl px-4 py-3 text-sm leading-6 whitespace-pre-line ${message.role === "user" ? "ml-auto bg-blue-600 text-white" : "border border-zinc-200 bg-white text-zinc-700"}`}
          >
            {message.text}
          </p>
        ))}
        {loading ? (
          <p role="status" className="text-sm text-zinc-500">
            증권에서 답을 찾고 있어요.
          </p>
        ) : null}
      </div>
      <form onSubmit={submit} className="border-t border-zinc-100 p-4">
        <label htmlFor="insurance-question" className="sr-only">
          보험 질문
        </label>
        <div className="flex gap-2">
          <input
            id="insurance-question"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="예: 암 진단비가 얼마예요?"
            className="min-w-0 flex-1 rounded-xl border border-zinc-300 px-4 py-3 text-sm outline-none focus:border-blue-600"
          />
          <button
            disabled={!question.trim() || loading}
            className="rounded-xl bg-blue-600 px-4 text-sm font-semibold text-white disabled:opacity-40"
          >
            질문하기
          </button>
        </div>
        <p className="mt-2 text-[11px] leading-4 text-zinc-400">
          보상 여부와 약관 조건은 추가 확인이 필요할 수 있어요.
        </p>
      </form>
    </aside>
  );
}
