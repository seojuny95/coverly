"use client";

import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { ANALYSIS_ROUTES } from "@/features/analysis/routes";
import { cn } from "@/shared/lib/utils";

export function AnalysisContainer({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const chatIsFullPage = pathname === ANALYSIS_ROUTES.chat;

  return (
    <main
      className={cn(
        "flex min-h-dvh flex-col bg-white px-5 py-6 text-zinc-950 sm:px-6",
        chatIsFullPage && "h-dvh overflow-hidden",
      )}
    >
      <section className="mx-auto mt-10 flex min-h-0 w-full max-w-6xl flex-1 flex-col">
        {children}
      </section>
    </main>
  );
}
