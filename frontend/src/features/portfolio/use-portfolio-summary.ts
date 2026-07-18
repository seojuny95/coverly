"use client";

import { useQuery } from "@tanstack/react-query";
import type { AnalyzedInsurance } from "../insurance-analysis/insurance-analysis-store";
import {
  type DeathBenefitGuideInput,
  type PortfolioSummary,
  requestPortfolioSummary,
} from "./portfolio-api";
import { portfolioKey } from "./portfolio-key";

type SummaryState =
  | { status: "loading" }
  | { status: "success"; summary: PortfolioSummary }
  | { status: "error" };

function portfolioSummaryQueryKey(
  documents: AnalyzedInsurance[],
  deathBenefitContext: DeathBenefitGuideInput,
) {
  return [
    "portfolio-summary",
    portfolioKey(documents),
    deathBenefitContext.has_dependent_family,
    deathBenefitContext.has_minor_children,
    deathBenefitContext.has_major_debt,
  ] as const;
}

export function usePortfolioSummary(
  documents: AnalyzedInsurance[],
  deathBenefitContext: DeathBenefitGuideInput,
  portfolioSessionToken?: string,
) {
  const currentPortfolioKey = portfolioKey(documents);
  const query = useQuery({
    queryKey: portfolioSummaryQueryKey(documents, deathBenefitContext),
    queryFn: ({ signal }) => {
      if (!portfolioSessionToken) {
        throw new Error("Portfolio session is unavailable");
      }
      return requestPortfolioSummary(
        documents,
        deathBenefitContext,
        portfolioSessionToken,
        signal,
      );
    },
    enabled: documents.length > 0 && Boolean(portfolioSessionToken),
    placeholderData: (previousData, previousQuery) =>
      previousQuery?.queryKey[1] === currentPortfolioKey
        ? previousData
        : undefined,
  });

  const state: SummaryState = query.isSuccess
    ? { status: "success", summary: query.data }
    : query.isError
      ? { status: "error" }
      : { status: "loading" };

  // No useCallback here: query.refetch is already stable, and wrapping the
  // whole `query` object (which is a fresh reference every render) in
  // useCallback never actually memoized anything.
  return {
    state,
    isRefreshing: query.isFetching && query.isSuccess,
    retry: () => void query.refetch(),
  };
}
