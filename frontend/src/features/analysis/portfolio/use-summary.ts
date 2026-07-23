"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiResponseError } from "@/shared/api/client";
import type { AnalyzedInsurance } from "../store";
import {
  type DeathBenefitGuideInput,
  type PortfolioSummary,
  requestPortfolioOverview,
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
  status: "idle" | "pending" | "request_failed";
};

type OverviewState = {
  attemptId: number;
  key: string | null;
  status: "idle" | "pending" | "failed";
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
  onSessionExpired?: () => void,
) {
  const queryClient = useQueryClient();
  const currentPortfolioKey = portfolioKey(documents);
  const queryKey = portfolioSummaryQueryKey(documents, deathBenefitContext);
  const retryKey = JSON.stringify(queryKey);
  const retryAttemptId = useRef(0);
  const overviewAttemptId = useRef(0);
  const [retryState, setRetryState] = useState<RetryState>({
    attemptId: 0,
    key: null,
    status: "idle",
  });
  const [overviewState, setOverviewState] = useState<OverviewState>({
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
      ).catch((error: unknown) => {
        if (isExpiredSessionError(error)) onSessionExpired?.();
        throw error;
      });
    },
    enabled: documents.length > 0 && Boolean(portfolioSessionToken),
    placeholderData: (previousData, previousQuery) =>
      previousQuery?.queryKey[1] === currentPortfolioKey
        ? previousData
        : undefined,
  });

  const overviewMutation = useMutation({
    mutationFn: () => {
      if (!portfolioSessionToken) {
        throw new Error("Portfolio session is unavailable");
      }
      return requestPortfolioOverview(
        documents,
        deathBenefitContext,
        portfolioSessionToken,
      ).catch((error: unknown) => {
        if (isExpiredSessionError(error)) onSessionExpired?.();
        throw error;
      });
    },
  });

  const generateOverview = useCallback(async () => {
    const attemptId = ++overviewAttemptId.current;
    setOverviewState({ attemptId, key: retryKey, status: "pending" });

    let status: OverviewState["status"] = "idle";
    try {
      const overview = await overviewMutation.mutateAsync();
      queryClient.setQueryData<PortfolioSummary>(queryKey, (current) =>
        current ? { ...current, overview } : current,
      );
    } catch {
      status = "failed";
    }

    setOverviewState((current) =>
      current.attemptId === attemptId && current.key === retryKey
        ? { attemptId, key: retryKey, status }
        : current,
    );
  }, [overviewMutation, queryClient, queryKey, retryKey]);

  useEffect(() => {
    if (!query.data || query.data.overview || !portfolioSessionToken) return;
    if (overviewState.key === retryKey && overviewState.status !== "idle") {
      return;
    }

    void generateOverview();
  }, [
    generateOverview,
    overviewState.key,
    overviewState.status,
    portfolioSessionToken,
    query.data,
    retryKey,
  ]);

  const state: SummaryState = query.data
    ? { status: "success", summary: query.data }
    : query.isError
      ? { status: "error" }
      : { status: "loading" };

  const isCurrentRetry = retryState.key === retryKey;
  const isCurrentOverview = overviewState.key === retryKey;

  // No useCallback here: query.refetch is already stable, and wrapping the
  // whole `query` object (which is a fresh reference every render) in
  // useCallback never actually memoized anything.
  return {
    state,
    isRefreshing: query.isFetching && Boolean(query.data),
    isRetrying: isCurrentRetry && retryState.status === "pending",
    isOverviewRetrying: isCurrentOverview && overviewState.status === "pending",
    retryFailed: isCurrentRetry && retryState.status === "request_failed",
    overviewRetryFailed: isCurrentOverview && overviewState.status === "failed",
    retry: async () => {
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
    retryOverview: generateOverview,
  };
}

function isExpiredSessionError(error: unknown) {
  return error instanceof ApiResponseError && error.status === 403;
}
