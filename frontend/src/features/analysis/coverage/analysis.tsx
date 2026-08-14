"use client";

import { useState } from "react";

import { CoverageAnalysisPanel } from "./panel";
import { AnalysisLoading } from "./panel/analysis-loading";
import { DEFAULT_DEATH_BENEFIT_CONTEXT } from "./death-benefit-context";
import { PortfolioSummarySuspense } from "./summary-suspense";
import { useCoverageAnalysis } from "./use-analysis";
import type { DeathBenefitGuideInput } from "./types";
import { useInsuranceData, type AnalyzedInsurance } from "../session/store";

const EMPTY_DOCUMENTS: AnalyzedInsurance[] = [];

export function CoverageAnalysis() {
  const { analysis, sessionExpired, expireSession } = useInsuranceData();
  const [deathBenefitContext, setDeathBenefitContext] =
    useState<DeathBenefitGuideInput>(DEFAULT_DEATH_BENEFIT_CONTEXT);
  const documents = analysis?.insuranceDocuments ?? EMPTY_DOCUMENTS;

  if (!analysis) return null;

  return (
    <PortfolioSummarySuspense
      documents={documents}
      deathBenefitContext={DEFAULT_DEATH_BENEFIT_CONTEXT}
      portfolioSessionToken={analysis.portfolioSessionToken}
      sessionExpired={sessionExpired}
      onSessionExpired={expireSession}
      loadingFallback={<AnalysisLoading />}
      errorFallback={(retry) => (
        <CoverageAnalysisPanel
          status="error"
          deathBenefitContext={deathBenefitContext}
          onDeathBenefitContextChange={setDeathBenefitContext}
          policyCount={documents.length}
          onRetry={retry}
        />
      )}
    >
      <CoverageAnalysisResult
        documents={documents}
        portfolioSessionToken={analysis.portfolioSessionToken}
        sessionExpired={sessionExpired}
        onSessionExpired={expireSession}
        deathBenefitContext={deathBenefitContext}
        onDeathBenefitContextChange={setDeathBenefitContext}
      />
    </PortfolioSummarySuspense>
  );
}

function CoverageAnalysisResult({
  documents,
  portfolioSessionToken,
  sessionExpired,
  onSessionExpired,
  deathBenefitContext,
  onDeathBenefitContextChange,
}: {
  documents: AnalyzedInsurance[];
  portfolioSessionToken: string;
  sessionExpired: boolean;
  onSessionExpired: () => void;
  deathBenefitContext: DeathBenefitGuideInput;
  onDeathBenefitContextChange: (context: DeathBenefitGuideInput) => void;
}) {
  const coverage = useCoverageAnalysis({
    documents,
    deathBenefitContext,
    portfolioSessionToken,
    sessionExpired,
    onSessionExpired,
  });

  return (
    <CoverageAnalysisPanel
      status={coverage.state.status}
      summary={
        coverage.state.status === "success" ? coverage.state.summary : undefined
      }
      deathBenefitContext={deathBenefitContext}
      onDeathBenefitContextChange={onDeathBenefitContextChange}
      isDeathBenefitRefreshing={coverage.isRefreshing}
      refreshFailed={coverage.refreshFailed}
      policyCount={documents.length}
      onRetry={coverage.retry}
      isRetrying={coverage.isRetrying}
      retryFailed={coverage.retryFailed}
      onRetryOverview={coverage.retryOverview}
      isOverviewRetrying={coverage.isOverviewRetrying}
      overviewRetryFailed={coverage.overviewRetryFailed}
      overviewUnavailable={coverage.overviewUnavailable}
    />
  );
}
