"use client";

import { useEffect, useRef, useState } from "react";
import type { AnalyzedInsurance } from "../insurance-analysis/insurance-analysis-store";
import {
  type PortfolioAnalysisResult,
  requestPortfolioAnalysis,
} from "./portfolio-api";

export function PortfolioAnalysisPanel({
  active,
  documents,
}: {
  active: boolean;
  documents: AnalyzedInsurance[];
}) {
  const [state, setState] = useState<{
    status: "idle" | "loading" | "success" | "error";
    result?: PortfolioAnalysisResult;
  }>({ status: "idle" });
  const [attempt, setAttempt] = useState(0);
  const requestedKey = useRef<string | null>(null);
  const portfolioKey = documents
    .map((document) => `${document.id}:${document.result.문자수}`)
    .join("|");

  useEffect(() => {
    const requestKey = `${portfolioKey}:${attempt}`;
    if (!active || requestedKey.current === requestKey) return;
    requestedKey.current = requestKey;
    setState({ status: "loading" });
    const controller = new AbortController();
    void requestPortfolioAnalysis(documents, controller.signal)
      .then((result) => setState({ status: "success", result }))
      .catch((error: unknown) => {
        if ((error as { name?: string }).name !== "AbortError")
          setState({ status: "error" });
      });
    // The request intentionally continues while another tab is visible.
  }, [active, attempt, documents, portfolioKey]);

  if (state.status === "idle" || state.status === "loading")
    return <AnalysisLoading />;
  if (state.status === "error")
    return (
      <section className="rounded-2xl border border-zinc-200 p-8 text-center">
        <h2 className="text-xl font-semibold">분석 결과를 불러오지 못했어요</h2>
        <p className="mt-2 text-sm text-zinc-500">잠시 후 다시 시도해주세요.</p>
        <button
          className="mt-5 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white"
          onClick={() => {
            setState({ status: "idle" });
            setAttempt((value) => value + 1);
          }}
        >
          다시 분석하기
        </button>
      </section>
    );
  const result = state.result!;
  return (
    <div className="space-y-5">
      {result.status === "partial" ? (
        <p
          role="status"
          className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900"
        >
          일부 보험은 확인하지 못했어요. 확인된 내용부터 보여드려요.
        </p>
      ) : null}
      <section className="rounded-2xl border border-zinc-200 p-6">
        <h2 className="text-xl font-semibold">내 보험을 전체로 살펴봤어요</h2>
        <dl className="mt-5 grid gap-4 sm:grid-cols-3">
          <AnalysisMetric label="보험" value={`${result.policy_count}개`} />
          <AnalysisMetric
            label="확인한 정액 보장"
            value={`${result.confirmed_total_count}개`}
          />
          <AnalysisMetric
            label="확인한 보험금 합계"
            value={formatWon(result.confirmed_total_amount)}
          />
        </dl>
      </section>
      <div className="grid gap-4 md:grid-cols-2">
        {result.classifications.map((section) => (
          <section
            key={section.classification}
            className="rounded-2xl border border-zinc-200 p-6"
          >
            <h3 className="font-semibold">{section.classification}</h3>
            <dl className="mt-4 space-y-2 text-sm text-zinc-600">
              <AnalysisRow label="보험" value={`${section.policy_count}개`} />
              <AnalysisRow
                label="정액 보장 합계"
                value={formatWon(section.confirmed_total_amount)}
              />
              <AnalysisRow
                label="실손형 담보"
                value={`${section.indemnity_coverage_count}개`}
              />
              <AnalysisRow
                label="확인이 필요한 담보"
                value={`${section.excluded_coverage_count}개`}
              />
            </dl>
          </section>
        ))}
      </div>
      {result.notices?.map((notice) => (
        <p key={notice} className="text-xs leading-5 text-zinc-500">
          {notice}
        </p>
      ))}
    </div>
  );
}

function AnalysisMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-zinc-50 px-4 py-4">
      <dt className="text-xs text-zinc-500">{label}</dt>
      <dd className="mt-2 font-semibold text-zinc-900">{value}</dd>
    </div>
  );
}

function AnalysisRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4">
      <dt>{label}</dt>
      <dd className="font-medium text-zinc-800">{value}</dd>
    </div>
  );
}

function formatWon(amount: number) {
  return `${amount.toLocaleString("ko-KR")}원`;
}

function AnalysisLoading() {
  return (
    <section
      aria-live="polite"
      className="rounded-2xl border border-zinc-200 p-8"
    >
      <div className="h-2 w-20 animate-pulse rounded bg-blue-600" />
      <h2 className="mt-5 text-xl font-semibold">내 보험을 분석하고 있어요</h2>
      <p className="mt-2 text-sm text-zinc-500">
        업로드한 증권의 보장을 종류별로 살펴보고 있어요.
      </p>
      <div className="mt-7 grid gap-4 md:grid-cols-2">
        {[1, 2, 3, 4].map((item) => (
          <div
            key={item}
            className="h-32 animate-pulse rounded-xl bg-zinc-100"
          />
        ))}
      </div>
    </section>
  );
}
