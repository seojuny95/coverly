"use client";

import { useQuery } from "@tanstack/react-query";
import { useCallback } from "react";
import type { AnalyzedInsurance } from "../insurance-analysis/insurance-analysis-store";
import {
  type PortfolioSummary,
  requestPortfolioSummary,
} from "./portfolio-api";

type SummaryState =
  | { status: "loading" }
  | { status: "success"; summary: PortfolioSummary }
  | { status: "error" };

function portfolioKey(documents: AnalyzedInsurance[]): string {
  return documents
    .map((document) => `${document.id}:${document.result.문자수}`)
    .join("|");
}

export function usePortfolioSummary(documents: AnalyzedInsurance[]) {
  const query = useQuery({
    queryKey: ["portfolio-summary", portfolioKey(documents)],
    queryFn: ({ signal }) => requestPortfolioSummary(documents, signal),
    enabled: documents.length > 0,
  });

  const state: SummaryState = query.isSuccess
    ? { status: "success", summary: query.data }
    : query.isError
      ? { status: "error" }
      : { status: "loading" };

  const retry = useCallback(() => {
    void query.refetch();
  }, [query]);

  return { state, retry };
}
