"use client";

import Link from "next/link";

import { useInsuranceData } from "./store";
import { Button } from "@/shared/components/ui/button";

export function SamplePortfolioNotice() {
  const { analysis } = useInsuranceData();

  if (analysis?.portfolioKind !== "sample") return null;

  return (
    <aside className="mb-6 flex flex-col gap-3 rounded-2xl border border-blue-200 bg-blue-50 px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-5">
      <div>
        <p className="text-sm font-semibold text-blue-950">
          샘플 보험 데이터로 확인하고 있어요
        </p>
        <p className="mt-1 text-sm leading-6 text-blue-800">
          실제 가입 내용이 아닌 가상 증권 4개의 분석 결과예요.
        </p>
      </div>
      <Button
        asChild
        variant="outline"
        className="border-blue-200 bg-white text-blue-700 hover:border-blue-300 hover:bg-blue-100"
      >
        <Link href="/upload">내 증권으로 분석하기</Link>
      </Button>
    </aside>
  );
}
