import { render, type RenderOptions } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement, ReactNode } from "react";
import {
  InsuranceDataProvider,
  type InsuranceAnalysis,
} from "../features/insurance-analysis/insurance-analysis-store";

export function makeTestQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
}

export function renderWithProviders(
  ui: ReactElement,
  options?: Omit<RenderOptions, "wrapper"> & {
    queryClient?: QueryClient;
    initialAnalysis?: InsuranceAnalysis | null;
  },
) {
  const queryClient = options?.queryClient ?? makeTestQueryClient();
  const initialAnalysis = options?.initialAnalysis ?? null;
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <InsuranceDataProvider initialAnalysis={initialAnalysis}>
          {children}
        </InsuranceDataProvider>
      </QueryClientProvider>
    );
  }
  return { queryClient, ...render(ui, { wrapper: Wrapper, ...options }) };
}
