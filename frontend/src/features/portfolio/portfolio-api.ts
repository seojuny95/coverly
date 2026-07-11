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
    original_amount?: string;
    major_category?: string;
    cross_insurer_duplicate: boolean;
  }>;
  excluded_coverages: Array<{
    policy_id?: string;
    insurer?: string;
    product_name?: string;
    coverage_name: string;
    major_category?: string;
    original_amount?: string;
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
  age: number | null;
  gender: string;
  life_stage: string;
  prepared_coverages: string[];
  coverage_gaps: Array<{ category: string; reason: string }>;
  baseline_notice: string;
  classifications: ClassificationAnalysis[];
  notices: string[];
  evidence?: Array<{
    id?: string;
    label?: string;
    detail?: string;
    fact?: string;
    policy_id?: string;
    insurer?: string;
    product_name?: string;
    coverage_name?: string;
    amount?: number;
  }>;
  limitations?: string[];
  demographics?: {
    age: number | null;
    gender: string;
    source: "policy" | "user" | "unknown";
  };
  counselor?: {
    overview: string;
    strengths: ReviewItem[];
    gaps: ReviewItem[];
    amount_review_items: AmountReviewItem[];
    next_questions: string[];
    next_steps: string[];
  };
  generation?: "llm" | "fallback";
};

export type ReviewItem = {
  title: string;
  detail: string;
  evidence_ids: string[];
};

export type AmountReviewItem = {
  coverage_name: string;
  current_amount: number | null;
  title: string;
  guidance: string;
  rationale: string;
  suggested_range: string | null;
  confidence: "high" | "medium" | "low";
  evidence_ids: string[];
};

export type QaAnswer = {
  status: "answered" | "refused" | "no_data";
  answer: string;
  citations: Array<{
    policy_id?: string;
    insurer?: string;
    product_name?: string;
    coverage_name?: string;
    evidence_id?: string;
  }>;
  limitations: string[];
  suggested_questions?: string[];
  suggestions?: string[];
  generation?: "llm" | "fallback";
  sections?: Array<{
    title: string;
    content: string;
    basis: "confirmed_fact" | "general_guidance";
  }>;
};

export type ChatHistoryItem = {
  role: "user" | "assistant";
  content: string;
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
  demographics: {
    age: number;
    gender: string;
    source?: "policy" | "user" | "unknown";
  },
  signal?: AbortSignal,
) {
  return post<PortfolioAnalysisResult>(
    "/portfolio/analysis",
    {
      policies: toPolicies(insuranceDocuments),
      demographics: {
        age: demographics.age,
        gender: demographics.gender,
        source: demographics.source ?? "user",
      },
    },
    signal,
  );
}

export function askPortfolioQuestion(
  question: string,
  insuranceDocuments: AnalyzedInsurance[],
  history: ChatHistoryItem[],
) {
  const demographics = getPolicyDemographics(insuranceDocuments);
  return post<QaAnswer>("/qa", {
    question: normalizeQuestion(question),
    policies: toPolicies(insuranceDocuments),
    demographics,
    history: prepareChatHistory(history),
  });
}

export function normalizeQuestion(question: string) {
  return question.trim().slice(0, 500);
}

export function prepareChatHistory(history: ChatHistoryItem[]) {
  return history.slice(-12).map((message) => ({
    role: message.role,
    content: message.content.slice(0, 1_000),
  }));
}

function getPolicyDemographics(insuranceDocuments: AnalyzedInsurance[]) {
  for (const document of insuranceDocuments) {
    if (document.result.기본정보?.보험분류?.includes("자동차")) continue;
    const info = document.result.기본정보?.피보험자정보;
    if (typeof info?.나이 === "number" && info.성별) {
      return { age: info.나이, gender: info.성별, source: "policy" as const };
    }
  }
  return { age: null, gender: "미상", source: "unknown" as const };
}
