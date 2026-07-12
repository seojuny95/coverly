"use client";

import { useQuery } from "@tanstack/react-query";
import type { AnalyzedInsurance } from "../insurance-analysis/insurance-analysis-store";
import { isAnalyzableDocument, isAutoInsurance } from "./analysis-eligibility";
import {
  type PortfolioAnalysisResult,
  requestPortfolioAnalysis,
} from "./portfolio-api";

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
  for (const document of documents) {
    if (isAutoInsurance(document.result)) continue;
    const info = document.result.기본정보?.피보험자정보;
    if (typeof info?.나이 === "number" && info.성별) {
      const demographics: Demographics = {
        age: info.나이,
        gender: info.성별,
        lifeStage: info.생애단계,
        source: "policy",
      };
      candidates.set(
        `${demographics.age}:${demographics.gender}`,
        demographics,
      );
    }
  }
  if (candidates.size !== 1) return null;
  return candidates.values().next().value ?? null;
}

export function usePortfolioAnalysis(
  documents: AnalyzedInsurance[],
  demographics: Demographics | null,
) {
  const eligible = documents.filter(isAnalyzableDocument);
  const portfolioKey = eligible
    .map((document) => `${document.id}:${document.result.문자수}`)
    .join("|");

  const query = useQuery({
    queryKey: [
      "portfolio-analysis",
      portfolioKey,
      demographics?.age,
      demographics?.gender,
    ],
    queryFn: ({ signal }) =>
      requestPortfolioAnalysis(documents, demographics!, signal),
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
