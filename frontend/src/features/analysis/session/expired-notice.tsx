"use client";

import Link from "next/link";

import { useInsuranceData } from "./store";
import { Button } from "@/shared/components/ui/button";

export function SessionExpiredNotice() {
  const { sessionExpired } = useInsuranceData();

  if (!sessionExpired) return null;

  return (
    <div
      role="status"
      className="mb-6 rounded-xl border border-amber-200 bg-amber-50 px-5 py-4 text-sm text-amber-950"
    >
      <p className="font-semibold">분석 세션이 만료됐어요</p>
      <p className="mt-1 leading-6">
        개인정보 보호를 위해 업로드한 문서 연결이 종료되었어요. 다시 분석하려면
        보험증권을 다시 올려주세요.
      </p>
      <Button asChild className="mt-3">
        <Link href="/upload">보험증권 다시 올리기</Link>
      </Button>
    </div>
  );
}
