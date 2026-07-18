"use client";

import { SectionLabel } from "./section-label";
import { BrandLink } from "./brand";
import { Button } from "./ui/button";

type ErrorScreenProps = {
  digest?: string;
  onRetry?: () => void;
  showBrand?: boolean;
};

export function ErrorScreen({
  digest,
  onRetry,
  showBrand = false,
}: ErrorScreenProps) {
  return (
    <main className="relative flex min-h-screen items-center justify-center bg-white px-5 py-12 text-zinc-950">
      {showBrand ? <BrandLink className="absolute top-6 left-6" /> : null}
      <section className="w-full max-w-md rounded-2xl border border-zinc-200 bg-white px-6 py-8 shadow-[10px_10px_0_#e8edff] sm:px-8">
        <SectionLabel>SYSTEM MESSAGE</SectionLabel>
        <h1 className="mt-5 text-2xl leading-8 font-semibold tracking-[-0.04em]">
          화면을 불러오지 못했어요.
        </h1>
        <p className="mt-3 text-sm leading-6 text-zinc-500">
          일시적인 오류일 수 있어요. 다시 시도해도 같은 문제가 계속되면 잠시 후
          다시 접속해주세요.
        </p>
        {digest ? (
          <p className="mt-4 rounded-xl border border-zinc-100 bg-zinc-50 px-3 py-2 font-mono text-xs text-zinc-500">
            오류 ID: {digest}
          </p>
        ) : null}
        {onRetry ? (
          <Button type="button" onClick={onRetry} className="mt-6">
            다시 시도하기
          </Button>
        ) : null}
      </section>
    </main>
  );
}
