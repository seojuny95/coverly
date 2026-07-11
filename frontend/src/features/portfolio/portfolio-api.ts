import type { AnalyzedInsurance } from "../insurance-analysis/insurance-analysis-store";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type CoverageTotal = {
  category: string;
  majorCategory: string;
  totalAmount: number;
  coverageCount: number;
  normalizedName: string;
  composition: Array<{
    policy_id?: string;
    insurer?: string;
    product_name?: string;
    coverage_name: string;
    amount: number;
    original_amount: string;
  }>;
};

export type PortfolioSummary = {
  totals: CoverageTotal[];
  indemnity_coverages: Array<{
    policy_id?: string;
    insurer?: string;
    product_name?: string;
    coverage_name: string;
    cross_insurer_duplicate: boolean;
  }>;
  excluded_coverages: Array<{
    policy_id?: string;
    coverage_name: string;
    original_amount: string;
    reason: string;
  }>;
  excluded_auto_policy_count: number;
};

export type ClassificationAnalysis = {
  classification: string;
  policy_count: number;
  confirmed_total_count: number;
  confirmed_total_amount: number;
  indemnity_coverage_count: number;
  excluded_coverage_count: number;
};

export type PortfolioAnalysisResult = {
  status: "complete" | "partial" | "empty";
  policy_count: number;
  classification_count: number;
  confirmed_total_count: number;
  confirmed_total_amount: number;
  indemnity_coverage_count: number;
  excluded_coverage_count: number;
  excluded_auto_policy_count: number;
  age: number;
  gender: string;
  life_stage: string;
  prepared_coverages: string[];
  coverage_gaps: Array<{ category: string; reason: string }>;
  baseline_notice: string;
  classifications: ClassificationAnalysis[];
  notices: string[];
};

export type QaAnswer = {
  status: "answered" | "refused" | "no_data";
  answer: string;
  citations: Array<{
    policy_id?: string;
    insurer?: string;
    product_name?: string;
    coverage_name?: string;
  }>;
  limitations: string[];
};

async function post<T>(path: string, body: unknown, signal?: AbortSignal) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok) throw new Error(`Request failed: ${response.status}`);
  return (await response.json()) as T;
}

function toPolicies(insuranceDocuments: AnalyzedInsurance[]) {
  return insuranceDocuments.map(({ id, result }) => ({
    id,
    기본정보: result.기본정보,
    보장목록: result.보장목록,
    분석상태: result.분석상태,
  }));
}

export function requestPortfolioSummary(
  insuranceDocuments: AnalyzedInsurance[],
  signal?: AbortSignal,
) {
  return post<PortfolioSummary>(
    "/portfolio/summary",
    { policies: toPolicies(insuranceDocuments) },
    signal,
  );
}

export function requestPortfolioAnalysis(
  insuranceDocuments: AnalyzedInsurance[],
  demographics: { age: number; gender: string },
  signal?: AbortSignal,
) {
  return post<PortfolioAnalysisResult>(
    "/portfolio/analysis",
    { policies: toPolicies(insuranceDocuments), ...demographics },
    signal,
  );
}

export function askPortfolioQuestion(
  question: string,
  insuranceDocuments: AnalyzedInsurance[],
) {
  return post<QaAnswer>("/qa", {
    question,
    policies: toPolicies(insuranceDocuments),
  });
}
