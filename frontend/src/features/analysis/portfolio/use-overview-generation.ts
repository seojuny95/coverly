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
  enabled,
}: {
  documents: AnalyzedInsurance[];
  deathBenefitContext: DeathBenefitGuideInput;
  portfolioSessionToken?: string;
  queryKey: QueryKey;
  retryKey: string;
  summary?: PortfolioSummary;
  onSessionExpired?: () => void;
  enabled: boolean;
}) {
  const queryClient = useQueryClient();
  const overviewAttemptId = useRef(0);
  const overviewRequest = useRef<AbortController | null>(null);
  const enabledRef = useRef(enabled);
  const [overviewState, setOverviewState] = useState<OverviewState>({
    attemptId: 0,
    key: null,
    status: "idle",
  });

  useEffect(() => {
    enabledRef.current = enabled;
  }, [enabled]);

  const overviewMutation = useMutation({
    mutationFn: (signal: AbortSignal) => {
      if (!portfolioSessionToken) {
        throw new Error("Portfolio session is unavailable");
      }
      return requestPortfolioOverview(
        documents,
        deathBenefitContext,
        portfolioSessionToken,
        signal,
      ).catch((error: unknown) => {
        if (!signal.aborted && isExpiredSessionError(error)) {
          onSessionExpired?.();
        }
        throw error;
      });
    },
  });

  const generateOverview = useCallback(async () => {
    if (!enabledRef.current) return;

    overviewRequest.current?.abort();
    const controller = new AbortController();
    overviewRequest.current = controller;
    const attemptId = ++overviewAttemptId.current;
    setOverviewState({ attemptId, key: retryKey, status: "pending" });

    let status: OverviewState["status"] = "idle";
    try {
      const overview = await overviewMutation.mutateAsync(controller.signal);
      if (!enabledRef.current || controller.signal.aborted) return;
      queryClient.setQueryData<PortfolioSummary>(queryKey, (current) =>
        current ? { ...current, overview } : current,
      );
    } catch {
      if (!controller.signal.aborted) status = "failed";
    } finally {
      if (overviewRequest.current === controller) {
        overviewRequest.current = null;
      }
    }

    setOverviewState((current) =>
      current.attemptId === attemptId && current.key === retryKey
        ? { attemptId, key: retryKey, status }
        : current,
    );
  }, [overviewMutation, queryClient, queryKey, retryKey]);

  useEffect(
    () => () => {
      overviewRequest.current?.abort();
      overviewRequest.current = null;
    },
    [retryKey],
  );

  useEffect(() => {
    if (!enabled || !summary || summary.overview || !portfolioSessionToken)
      return;
    if (overviewState.key === retryKey && overviewState.status !== "idle") {
      return;
    }

    void generateOverview();
  }, [
    generateOverview,
    enabled,
    overviewState.key,
    overviewState.status,
    portfolioSessionToken,
    retryKey,
    summary,
  ]);

  const isCurrentOverview = overviewState.key === retryKey;

  return {
    isOverviewRetrying:
      enabled && isCurrentOverview && overviewState.status === "pending",
    overviewRetryFailed:
      enabled && isCurrentOverview && overviewState.status === "failed",
    retryOverview: generateOverview,
  };
}
