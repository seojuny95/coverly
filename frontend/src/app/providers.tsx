"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { InsuranceDataProvider } from "../features/insurance-analysis/insurance-analysis-store";

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
      <InsuranceDataProvider>{children}</InsuranceDataProvider>
    </QueryClientProvider>
  );
}

export default Providers;
