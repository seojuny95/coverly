"use client";

import {
  useMutation,
  useQueryClient,
  type QueryKey,
} from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import type { AnalyzedInsurance } from "../store";
import { requestPortfolioOverview } from "./api";
import { isExpiredSessionError } from "./session-errors";
import type { DeathBenefitGuideInput, PortfolioSummary } from "./api";

type OverviewState = {
  attemptId: number;
  key: string | null;
  status: "idle" | "pending" | "failed";
};

export function usePortfolioOverviewGeneration({
  documents,
  deathBenefitContext,
  portfolioSessionToken,
  queryKey,
  retryKey,
  summary,
  onSessionExpired,
}: {
  documents: AnalyzedInsurance[];
  deathBenefitContext: DeathBenefitGuideInput;
  portfolioSessionToken?: string;
  queryKey: QueryKey;
  retryKey: string;
  summary?: PortfolioSummary;
  onSessionExpired?: () => void;
}) {
  const queryClient = useQueryClient();
  const overviewAttemptId = useRef(0);
  const [overviewState, setOverviewState] = useState<OverviewState>({
    attemptId: 0,
    key: null,
    status: "idle",
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
    if (!summary || summary.overview || !portfolioSessionToken) return;
    if (overviewState.key === retryKey && overviewState.status !== "idle") {
      return;
    }

    void generateOverview();
  }, [
    generateOverview,
    overviewState.key,
    overviewState.status,
    portfolioSessionToken,
    retryKey,
    summary,
  ]);

  const isCurrentOverview = overviewState.key === retryKey;

  return {
    isOverviewRetrying: isCurrentOverview && overviewState.status === "pending",
    overviewRetryFailed: isCurrentOverview && overviewState.status === "failed",
    retryOverview: generateOverview,
  };
}
