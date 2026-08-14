"use client";

import {
  QueryErrorResetBoundary,
  useSuspenseQuery,
} from "@tanstack/react-query";
import { Component, Suspense, type ReactNode } from "react";

import type { AnalyzedInsurance } from "../session/store";
import type { DeathBenefitGuideInput } from "./types";
import { portfolioSummaryQueryKey } from "./query-key";
import { portfolioSummaryQueryOptions } from "./summary-query";

type Props = {
  children: ReactNode;
  documents: AnalyzedInsurance[];
  deathBenefitContext: DeathBenefitGuideInput;
  portfolioSessionToken?: string;
  sessionExpired: boolean;
  onSessionExpired: () => void;
  loadingFallback: ReactNode;
  errorFallback: (retry: () => void) => ReactNode;
};

export function PortfolioSummarySuspense({
  children,
  documents,
  deathBenefitContext,
  portfolioSessionToken,
  sessionExpired,
  onSessionExpired,
  loadingFallback,
  errorFallback,
}: Props) {
  if (documents.length === 0 || !portfolioSessionToken || sessionExpired) {
    return children;
  }

  const resetKey = JSON.stringify(
    portfolioSummaryQueryKey(documents, deathBenefitContext),
  );

  return (
    <QueryErrorResetBoundary>
      {({ reset }) => (
        <SummaryErrorBoundary
          key={resetKey}
          fallback={errorFallback}
          onReset={reset}
        >
          <Suspense fallback={loadingFallback}>
            <PortfolioSummaryLoader
              documents={documents}
              deathBenefitContext={deathBenefitContext}
              portfolioSessionToken={portfolioSessionToken}
              onSessionExpired={onSessionExpired}
            >
              {children}
            </PortfolioSummaryLoader>
          </Suspense>
        </SummaryErrorBoundary>
      )}
    </QueryErrorResetBoundary>
  );
}

function PortfolioSummaryLoader({
  children,
  documents,
  deathBenefitContext,
  portfolioSessionToken,
  onSessionExpired,
}: Omit<
  Props,
  | "portfolioSessionToken"
  | "sessionExpired"
  | "loadingFallback"
  | "errorFallback"
> & { portfolioSessionToken: string }) {
  useSuspenseQuery(
    portfolioSummaryQueryOptions({
      documents,
      deathBenefitContext,
      portfolioSessionToken,
      onSessionExpired,
    }),
  );

  return children;
}

class SummaryErrorBoundary extends Component<
  {
    children: ReactNode;
    fallback: (retry: () => void) => ReactNode;
    onReset: () => void;
  },
  { error: unknown | null }
> {
  state: { error: unknown | null } = { error: null };

  static getDerivedStateFromError(error: unknown) {
    return { error };
  }

  private retry = () => {
    this.props.onReset();
    this.setState({ error: null });
  };

  render() {
    if (this.state.error) return this.props.fallback(this.retry);
    return this.props.children;
  }
}
