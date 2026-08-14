"use client";

import type { AnalyzedInsurance } from "../session/store";
import { CoverageTotalTable } from "../coverage/total-table";
import { DEFAULT_DEATH_BENEFIT_CONTEXT } from "../coverage/death-benefit-context";
import { PortfolioSummarySuspense } from "../coverage/summary-suspense";
import { usePortfolioSummary } from "../coverage/use-summary";

const ignoreRetry = () => undefined;

export function PolicySummarySection({
  documents,
  portfolioSessionToken,
  sessionExpired,
  onSessionExpired,
}: {
  documents: AnalyzedInsurance[];
  portfolioSessionToken: string;
  sessionExpired: boolean;
  onSessionExpired: () => void;
}) {
  return (
    <PortfolioSummarySuspense
      documents={documents}
      deathBenefitContext={DEFAULT_DEATH_BENEFIT_CONTEXT}
      portfolioSessionToken={portfolioSessionToken}
      sessionExpired={sessionExpired}
      onSessionExpired={onSessionExpired}
      loadingFallback={
        <CoverageTotalTable status="loading" onRetry={ignoreRetry} />
      }
      errorFallback={(retry) => (
        <CoverageTotalTable status="error" onRetry={retry} />
      )}
    >
      <PolicySummaryResult
        documents={documents}
        portfolioSessionToken={portfolioSessionToken}
        sessionExpired={sessionExpired}
        onSessionExpired={onSessionExpired}
      />
    </PortfolioSummarySuspense>
  );
}

function PolicySummaryResult({
  documents,
  portfolioSessionToken,
  sessionExpired,
  onSessionExpired,
}: {
  documents: AnalyzedInsurance[];
  portfolioSessionToken: string;
  sessionExpired: boolean;
  onSessionExpired: () => void;
}) {
  const summary = usePortfolioSummary(
    documents,
    DEFAULT_DEATH_BENEFIT_CONTEXT,
    portfolioSessionToken,
    onSessionExpired,
    sessionExpired,
  );

  return (
    <CoverageTotalTable
      status={summary.state.status}
      summary={
        summary.state.status === "success" ? summary.state.summary : undefined
      }
      onRetry={summary.retry}
      isRetrying={summary.isRetrying}
      retryFailed={summary.retryFailed}
    />
  );
}
