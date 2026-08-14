"use client";

import type { AnalyzedInsurance } from "../session/store";
import type { DeathBenefitGuideInput } from "./types";
import { usePortfolioOverviewGeneration } from "./use-overview-generation";
import { usePortfolioSummary } from "./use-summary";

export function useCoverageAnalysis({
  documents,
  deathBenefitContext,
  portfolioSessionToken,
  sessionExpired,
  onSessionExpired,
}: {
  documents: AnalyzedInsurance[];
  deathBenefitContext: DeathBenefitGuideInput;
  portfolioSessionToken?: string;
  sessionExpired: boolean;
  onSessionExpired: () => void;
}) {
  const summary = usePortfolioSummary(
    documents,
    deathBenefitContext,
    portfolioSessionToken,
    onSessionExpired,
    sessionExpired,
  );
  const overview = usePortfolioOverviewGeneration({
    documents,
    deathBenefitContext,
    portfolioSessionToken: sessionExpired ? undefined : portfolioSessionToken,
    summary: summary.data,
    onSessionExpired,
  });

  return {
    data: summary.data,
    state: summary.state,
    isRefreshing: summary.isRefreshing,
    refreshFailed: summary.refreshFailed,
    isRetrying: summary.isRetrying,
    retryFailed: summary.retryFailed,
    retry: summary.retry,
    isOverviewRetrying: overview.isOverviewRetrying,
    overviewRetryFailed: overview.overviewRetryFailed,
    retryOverview: overview.retryOverview,
    overviewUnavailable:
      sessionExpired &&
      summary.state.status === "success" &&
      !summary.state.summary.overview,
  };
}
