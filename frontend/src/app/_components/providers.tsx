"use client";

import {
  QueryClient,
  QueryClientProvider,
  useQueryClient,
} from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import {
  InsuranceDataProvider,
  useInsuranceData,
} from "@/features/analysis/session/store";
import { isAnalysisPath } from "@/features/analysis/routes";
import { removeAnalysisCache } from "@/features/analysis/query-cache";
import { TooltipProvider } from "@/shared/components/ui/tooltip";

// In-memory only: no persister. Cache is intentionally lost on full reload so
// sensitive policy data never lands in storage (no auth).
function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: Infinity,
        retry: 0,
        refetchOnWindowFocus: false,
      },
    },
  });
}

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(makeQueryClient);
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <InsuranceDataProvider>
          <AnalysisRouteScope>{children}</AnalysisRouteScope>
        </InsuranceDataProvider>
      </TooltipProvider>
    </QueryClientProvider>
  );
}

function AnalysisRouteScope({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const previousPathname = useRef(pathname);
  const queryClient = useQueryClient();
  const { clear } = useInsuranceData();

  useEffect(() => {
    const previous = previousPathname.current;
    if (
      previous !== pathname &&
      isAnalysisPath(previous) &&
      !isAnalysisPath(pathname)
    ) {
      removeAnalysisCache(queryClient);
      clear();
    }
    previousPathname.current = pathname;
  }, [clear, pathname, queryClient]);

  return children;
}
