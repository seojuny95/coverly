"use client";

import { useEffect, useState, useTransition } from "react";

import { BrandLink } from "./brand";
import { RetryButton } from "./retry-button";
import { SectionLabel } from "./section-label";

type ErrorScreenProps = {
  digest?: string;
  onRetry?: () => void | Promise<void>;
  showBrand?: boolean;
};

export function ErrorScreen({
  digest,
  onRetry,
  showBrand = false,
}: ErrorScreenProps) {
  const [isRetrying, startRetry] = useTransition();
  const [retryStatus, setRetryStatus] = useState<
    "idle" | "retrying" | "failed"
  >("idle");

  useEffect(() => {
    if (retryStatus !== "retrying" || isRetrying) return;

    // A successful boundary reset unmounts this screen. If it remains mounted
    // after the retry settles, the render failed again.
    const timeoutId = window.setTimeout(() => setRetryStatus("failed"), 0);
    return () => window.clearTimeout(timeoutId);
  }, [isRetrying, retryStatus]);

  const retryFailed = retryStatus === "failed";

  return (
    <main className="relative flex min-h-screen items-center justify-center bg-white px-5 py-12 text-zinc-950">
      {showBrand ? <BrandLink className="absolute top-6 left-6" /> : null}
      <section className="w-full max-w-md rounded-2xl border border-zinc-200 bg-white px-6 py-8 shadow-[10px_10px_0_#e8edff] sm:px-8">
        <SectionLabel>SYSTEM MESSAGE</SectionLabel>
        <h1
          role={retryFailed ? "alert" : undefined}
          className="mt-5 text-2xl leading-8 font-semibold tracking-[-0.04em]"
        >
          {retryFailed
            ? "화면을 다시 불러오지 못했어요."
            : "화면을 불러오지 못했어요."}
        </h1>
        <p className="mt-3 text-sm leading-6 text-zinc-500">
          {retryFailed
            ? "잠시 후 다시 시도하거나 처음 화면에서 다시 시작해주세요."
            : "일시적인 오류일 수 있어요. 다시 시도해도 같은 문제가 계속되면 잠시 후 다시 접속해주세요."}
        </p>
        {digest ? (
          <p className="mt-4 rounded-xl border border-zinc-100 bg-zinc-50 px-3 py-2 font-mono text-xs text-zinc-500">
            오류 ID: {digest}
          </p>
        ) : null}
        {onRetry ? (
          <RetryButton
            type="button"
            onClick={() => {
              setRetryStatus("retrying");
              startRetry(async () => {
                try {
                  await onRetry();
                } catch {
                  setRetryStatus("failed");
                }
              });
            }}
            className="mt-6"
            isPending={isRetrying}
            label="다시 시도하기"
            pendingLabel="다시 시도하는 중…"
          />
        ) : null}
      </section>
    </main>
  );
}
