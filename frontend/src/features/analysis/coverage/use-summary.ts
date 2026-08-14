"use client";

import {
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import { useRef, useState } from "react";
import type { AnalyzedInsurance } from "../session/store";
import type { DeathBenefitGuideInput, PortfolioSummary } from "./api";
import {
  PORTFOLIO_SUMMARY_QUERY_KEY,
  portfolioKey,
  portfolioSummaryQueryKey,
} from "./query-key";
import { portfolioSummaryQueryOptions } from "./summary-query";

type SummaryState =
  | { status: "loading" }
  | { status: "success"; summary: PortfolioSummary }
  | { status: "error" }
  | { status: "expired" };

type RetryState = {
  attemptId: number;
  key: string | null;
  status: "idle" | "pending" | "request_failed";
};

export function usePortfolioSummary(
  documents: AnalyzedInsurance[],
  deathBenefitContext: DeathBenefitGuideInput,
  portfolioSessionToken?: string,
  onSessionExpired?: () => void,
  sessionExpired = false,
) {
  const currentPortfolioKey = portfolioKey(documents);
  const queryKey = portfolioSummaryQueryKey(documents, deathBenefitContext);
  const retryKey = JSON.stringify(queryKey);
  const queryEnabled =
    documents.length > 0 && Boolean(portfolioSessionToken) && !sessionExpired;
  const retryAttemptId = useRef(0);
  const queryClient = useQueryClient();
  const [retryState, setRetryState] = useState<RetryState>({
    attemptId: 0,
    key: null,
    status: "idle",
  });
  const query = useQuery({
    ...portfolioSummaryQueryOptions({
      documents,
      deathBenefitContext,
      portfolioSessionToken: portfolioSessionToken ?? "",
      onSessionExpired,
    }),
    enabled: queryEnabled,
    placeholderData: (previousData, previousQuery) =>
      previousQuery?.queryKey[PORTFOLIO_SUMMARY_QUERY_KEY.length] ===
      currentPortfolioKey
        ? previousData
        : undefined,
  });
  const retainedSummary = query.isError
    ? findLatestPortfolioSummary(queryClient, currentPortfolioKey, retryKey)
    : undefined;
  const displayedSummary =
    query.data ?? (query.isError ? retainedSummary : undefined);

  const state: SummaryState = displayedSummary
    ? { status: "success", summary: displayedSummary }
    : sessionExpired
      ? { status: "expired" }
      : query.isError
        ? { status: "error" }
        : { status: "loading" };

  const isCurrentRetry = retryState.key === retryKey;

  // No useCallback here: query.refetch is already stable, and wrapping the
  // whole `query` object (which is a fresh reference every render) in
  // useCallback never actually memoized anything.
  return {
    data: query.data,
    state,
    isRefreshing: query.isFetching && Boolean(displayedSummary),
    refreshFailed: query.isError && Boolean(displayedSummary),
    isRetrying: isCurrentRetry && retryState.status === "pending",
    retryFailed: isCurrentRetry && retryState.status === "request_failed",
    retry: async () => {
      if (!queryEnabled) return;

      const attemptId = ++retryAttemptId.current;
      setRetryState({ attemptId, key: retryKey, status: "pending" });

      let status: RetryState["status"] = "request_failed";
      try {
        const result = await query.refetch();
        status = result.isError && !result.data ? "request_failed" : "idle";
      } catch {
        status = "request_failed";
      }

      setRetryState((current) =>
        current.attemptId === attemptId && current.key === retryKey
          ? { attemptId, key: retryKey, status }
          : current,
      );
    },
  };
}

function findLatestPortfolioSummary(
  queryClient: QueryClient,
  currentPortfolioKey: string,
  currentQueryKey: string,
): PortfolioSummary | undefined {
  let latest: { summary: PortfolioSummary; dataUpdatedAt: number } | undefined;

  const candidates = queryClient.getQueryCache().findAll({
    queryKey: [...PORTFOLIO_SUMMARY_QUERY_KEY, currentPortfolioKey],
  });

  for (const candidate of candidates) {
    if (JSON.stringify(candidate.queryKey) === currentQueryKey) continue;
    const summary = candidate.state.data as PortfolioSummary | undefined;
    if (!summary) continue;

    if (!latest || candidate.state.dataUpdatedAt >= latest.dataUpdatedAt) {
      latest = { summary, dataUpdatedAt: candidate.state.dataUpdatedAt };
    }
  }

  return latest?.summary;
}
