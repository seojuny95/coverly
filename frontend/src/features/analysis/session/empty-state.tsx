import Link from "next/link";

import { SectionLabel } from "@/shared/components/section-label";
import { Button } from "@/shared/components/ui/button";

export function AnalysisEmptyState() {
  return (
    <main className="relative flex min-h-screen items-center justify-center bg-white px-5 text-zinc-950">
      <section className="w-full max-w-lg rounded-2xl border border-zinc-200 bg-white px-6 py-8 text-center shadow-[10px_10px_0_#e8edff]">
        <div className="mb-5 flex justify-center">
          <SectionLabel>분석 결과</SectionLabel>
        </div>
        <h1 className="text-2xl font-semibold tracking-[-0.04em]">
          분석할 보험증권이 없어요
        </h1>
        <p className="mt-3 text-sm leading-6 text-zinc-500">
          보험증권 PDF를 올리면 AI가 정리한 결과를 여기에서 볼 수 있어요.
        </p>
        <Button asChild className="mt-6">
          <Link href="/upload">보험증권 올리기</Link>
        </Button>
      </section>
    </main>
  );
}
