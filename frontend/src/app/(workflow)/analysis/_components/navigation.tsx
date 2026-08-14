"use client";

import { useIsFetching } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { ANALYSIS_ROUTES } from "@/features/analysis/routes";
import { preloadInsuranceChatbot } from "@/features/analysis/chat/load-chatbot";
import { PORTFOLIO_SUMMARY_QUERY_KEY } from "@/features/analysis/coverage/query-key";
import { cn } from "@/shared/lib/utils";

const ITEMS = [
  { href: ANALYSIS_ROUTES.policies, label: "내 보험" },
  { href: ANALYSIS_ROUTES.coverage, label: "보험 분석" },
  { href: ANALYSIS_ROUTES.chat, label: "AI 보험 상담" },
] as const;

export function AnalysisNavigation() {
  const pathname = usePathname();
  const summaryRequestCount = useIsFetching({
    queryKey: PORTFOLIO_SUMMARY_QUERY_KEY,
  });

  return (
    <nav
      aria-label="보험 정보 보기"
      className="mb-8 flex gap-1 border-b border-zinc-200"
    >
      {ITEMS.map((item) => {
        const active = pathname === item.href;

        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            onMouseEnter={
              item.href === ANALYSIS_ROUTES.chat
                ? preloadInsuranceChatbot
                : undefined
            }
            onFocus={
              item.href === ANALYSIS_ROUTES.chat
                ? preloadInsuranceChatbot
                : undefined
            }
            className={cn(
              "inline-flex items-center border-b-2 px-5 py-3 text-sm font-semibold transition-colors",
              active
                ? "border-blue-600 text-blue-600"
                : "border-transparent text-zinc-500 hover:text-zinc-900",
            )}
          >
            {item.label}
            {item.href === ANALYSIS_ROUTES.coverage &&
            summaryRequestCount > 0 ? (
              <span className="ml-2 inline-flex items-center rounded-full bg-blue-50 px-2 py-0.5 text-[11px] font-medium text-blue-600">
                분석 중…
              </span>
            ) : null}
          </Link>
        );
      })}
    </nav>
  );
}
