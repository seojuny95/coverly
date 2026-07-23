"use client";

import { useQuery } from "@tanstack/react-query";
import { useRef, useState } from "react";
import type { AnalyzedInsurance } from "../store";
import {
  type DeathBenefitGuideInput,
  type PortfolioSummary,
  requestPortfolioSummary,
} from "./api";
import { portfolioKey } from "./query-key";

type SummaryState =
  | { status: "loading" }
  | { status: "success"; summary: PortfolioSummary }
  | { status: "error" };

type RetryState = {
  attemptId: number;
  key: string | null;
  status: "idle" | "pending" | "request_failed" | "overview_missing";
};

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
  const queryKey = portfolioSummaryQueryKey(documents, deathBenefitContext);
  const retryKey = JSON.stringify(queryKey);
  const retryAttemptId = useRef(0);
  const [retryState, setRetryState] = useState<RetryState>({
    attemptId: 0,
    key: null,
    status: "idle",
  });
  const query = useQuery({
    queryKey,
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

  const isCurrentRetry = retryState.key === retryKey;

  // No useCallback here: query.refetch is already stable, and wrapping the
  // whole `query` object (which is a fresh reference every render) in
  // useCallback never actually memoized anything.
  return {
    state,
    isRefreshing: query.isFetching && query.isSuccess,
    isRetrying: isCurrentRetry && retryState.status === "pending",
    retryFailed: isCurrentRetry && retryState.status === "request_failed",
    overviewRetryFailed:
      isCurrentRetry && retryState.status === "overview_missing",
    retry: async () => {
      const attemptId = ++retryAttemptId.current;
      setRetryState({ attemptId, key: retryKey, status: "pending" });

      let status: RetryState["status"] = "request_failed";
      try {
        const result = await query.refetch();
        status = result.isError
          ? "request_failed"
          : result.data?.overview
            ? "idle"
            : "overview_missing";
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
