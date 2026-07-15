"use client";

import { useQuery } from "@tanstack/react-query";
import type { AnalyzedInsurance } from "../insurance-analysis/insurance-analysis-store";
import {
  type PortfolioSummary,
  requestPortfolioSummary,
} from "./portfolio-api";
import { portfolioKey } from "./portfolio-key";

type SummaryState =
  | { status: "loading" }
  | { status: "success"; summary: PortfolioSummary }
  | { status: "error" };

function portfolioSummaryQueryKey(documents: AnalyzedInsurance[]) {
  return ["portfolio-summary", portfolioKey(documents)] as const;
}

export function usePortfolioSummary(documents: AnalyzedInsurance[]) {
  const query = useQuery({
    queryKey: portfolioSummaryQueryKey(documents),
    queryFn: ({ signal }) => requestPortfolioSummary(documents, signal),
    enabled: documents.length > 0,
  });

  const state: SummaryState = query.isSuccess
    ? { status: "success", summary: query.data }
    : query.isError
      ? { status: "error" }
      : { status: "loading" };

  // No useCallback here: query.refetch is already stable, and wrapping the
  // whole `query` object (which is a fresh reference every render) in
  // useCallback never actually memoized anything.
  return { state, retry: () => void query.refetch() };
}
