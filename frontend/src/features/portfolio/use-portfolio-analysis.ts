"use client";

import { useQuery } from "@tanstack/react-query";
import type { AnalyzedInsurance } from "../insurance-analysis/insurance-analysis-store";
import { isAnalyzableDocument } from "./analysis-eligibility";
import {
  type AnalysisContextAnswer,
  collectPolicyDemographicsCandidates,
  type PortfolioAnalysisResult,
  requestPortfolioAnalysis,
} from "./portfolio-api";
import { portfolioKey } from "./portfolio-key";

export type Demographics = {
  age: number;
  gender: string;
  lifeStage?: string;
  source?: "policy" | "user" | "unknown";
};

// One unambiguous policy-derived (age, gender) → auto; else null (ask the user).
export function deriveDemographics(
  documents: AnalyzedInsurance[],
): Demographics | null {
  const candidates = new Map<string, Demographics>();
  for (const candidate of collectPolicyDemographicsCandidates(documents)) {
    const demographics: Demographics = {
      age: candidate.age,
      gender: candidate.gender,
      lifeStage: candidate.lifeStage,
      source: "policy",
    };
    candidates.set(`${demographics.age}:${demographics.gender}`, demographics);
  }
  if (candidates.size !== 1) return null;
  return candidates.values().next().value ?? null;
}

export function usePortfolioAnalysis(
  documents: AnalyzedInsurance[],
  demographics: Demographics | null,
  personalContext: AnalysisContextAnswer[] = [],
) {
  const eligible = documents.filter(isAnalyzableDocument);

  const query = useQuery({
    // Keyed on the full document set — requestPortfolioAnalysis sends every
    // document (not just `eligible`) to the backend, so the cache key must
    // reflect what's actually in the request body or a change confined to a
    // non-eligible document would silently serve a stale cached result.
    queryKey: [
      "portfolio-analysis",
      portfolioKey(documents),
      demographics?.age,
      demographics?.gender,
      personalContext,
    ],
    queryFn: ({ signal }) =>
      requestPortfolioAnalysis(
        documents,
        demographics!,
        personalContext,
        signal,
      ),
    enabled: eligible.length > 0 && demographics != null,
  });

  const status: "idle" | "loading" | "success" | "error" = query.isSuccess
    ? "success"
    : query.isError
      ? "error"
      : query.fetchStatus === "idle" && !query.isFetched
        ? "idle"
        : "loading";

  return {
    status,
    result: query.data as PortfolioAnalysisResult | undefined,
    refetch: () => void query.refetch(),
  };
}
