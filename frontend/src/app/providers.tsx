"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import {
  InsuranceDataProvider,
  useInsuranceData,
} from "../features/insurance-analysis/insurance-analysis-store";

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
      <InsuranceDataProvider>
        <AnalysisRouteScope>{children}</AnalysisRouteScope>
      </InsuranceDataProvider>
    </QueryClientProvider>
  );
}

function AnalysisRouteScope({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const previousPathname = useRef(pathname);
  const { clear } = useInsuranceData();

  useEffect(() => {
    const previous = previousPathname.current;
    if (
      previous !== pathname &&
      previous === "/analysis" &&
      pathname !== "/analysis"
    ) {
      clear();
    }
    previousPathname.current = pathname;
  }, [clear, pathname]);

  return children;
}
