import Link from "next/link";

import { SectionLabel } from "@/shared/components/section-label";
import { Button } from "@/shared/components/ui/button";

import { InsuranceConnectionFlow } from "./insurance-connection-flow";

export function HomeHero() {
  return (
    <section className="relative mx-auto flex min-h-screen w-full max-w-6xl flex-col items-center justify-center px-6 pt-24 pb-10 text-center sm:pt-28 sm:pb-14 lg:px-8">
      <div className="animate-enter-overlay flex flex-col items-center">
        <div className="mb-6">
          <SectionLabel>보험을 팔지 않는 AI 보험 분석</SectionLabel>
        </div>

        <h1 className="max-w-5xl text-[2.25rem] leading-[1.04] font-semibold tracking-[-0.075em] [word-break:keep-all] text-zinc-950 sm:text-[clamp(3.5rem,7.2vw,6.7rem)] sm:leading-[1.01]">
          <span className="block whitespace-nowrap">흩어진 보험을 모아,</span>
          <span className="block whitespace-nowrap text-zinc-400">
            당신 편에서 분석해요.
          </span>
        </h1>

        <p className="mt-7 max-w-2xl text-base leading-7 [word-break:keep-all] text-zinc-600 sm:text-lg sm:leading-8">
          여러 보험사에 나뉜 가입 내역을 AI가 연결해 보장별로 정리하고,
          <br className="hidden sm:block" /> 모든 내용에 확인한 근거를 함께
          보여드려요.
        </p>

        <Button asChild className="mt-8">
          <Link href="/upload">내 보험 분석하기</Link>
        </Button>
        <p className="mt-3 text-xs text-zinc-400">
          상담 전화도, 가입 권유도 없어요.
        </p>
      </div>

      <InsuranceConnectionFlow />
    </section>
  );
}
