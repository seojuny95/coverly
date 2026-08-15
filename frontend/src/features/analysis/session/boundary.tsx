"use client";

import { useMemo, type ReactNode } from "react";

import { AnalysisEmptyState } from "./empty-state";
import { useBeforeUnloadGuard } from "./use-leave-guard";
import { usePortfolioSessionRefresh } from "./use-session-refresh";
import { useInsuranceData } from "./store";

export function AnalysisSessionBoundary({ children }: { children: ReactNode }) {
  const {
    analysis,
    hasData,
    sessionExpired,
    replacePortfolioSession,
    expireSession,
  } = useInsuranceData();

  useBeforeUnloadGuard(hasData);

  const session = useMemo(
    () =>
      analysis
        ? {
            portfolioSessionToken: analysis.portfolioSessionToken,
            expiresAt: analysis.portfolioSessionExpiresAt,
            counselTurnsRemaining: analysis.counselTurnsRemaining,
            portfolioKind: analysis.portfolioKind,
          }
        : undefined,
    [analysis],
  );

  usePortfolioSessionRefresh({
    session,
    enabled: hasData && !sessionExpired,
    onRefreshed: replacePortfolioSession,
    onExpired: expireSession,
  });

  if (!analysis || !hasData) return <AnalysisEmptyState />;

  return children;
}
