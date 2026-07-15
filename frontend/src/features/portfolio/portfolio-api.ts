import type { AnalyzedInsurance } from "../insurance-analysis/insurance-analysis-store";
import { isAutoInsurance } from "./analysis-eligibility";

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
  indemnity_coverage_count: number;
  indemnity_duplicate_count: number;
  excluded_coverage_count: number;
  excluded_auto_policy_count: number;
  age: number | null;
  gender: string;
  life_stage: string;
  prepared_coverages: string[];
  coverage_gaps: Array<{ category: string; reason: string }>;
  excluded_coverages: Array<{
    policy_id?: string;
    insurer?: string;
    product_name?: string;
    coverage_name: string;
    major_category?: string;
    original_amount?: string;
    reason: string;
  }>;
  premium: {
    monthly_total: number | null;
    monthly_policy_count: number;
    unconfirmed_policy_count: number;
    items: Array<{
      policy_id?: string;
      insurer?: string;
      product_name?: string;
      monthly_amount: number | null;
      cycle: string | null;
    }>;
  };
  premium_benchmark?: {
    age_band_label: string;
    min_age: number;
    max_age: number;
    average_monthly_income: number;
    suggested_min_ratio: number;
    suggested_max_ratio: number;
    suggested_min_premium: number;
    suggested_max_premium: number;
    income_source: {
      label: string;
      url: string;
      published_at: string;
      reliability: string;
      caveat: string;
    };
    guide_source: {
      label: string;
      url: string;
      published_at: string;
      reliability: string;
      caveat: string;
    };
  } | null;
  priority_checks?: Array<{
    kind: "premium" | "duplicate" | "coverage_gap" | "contract";
    title: string;
    detail: string;
    evidence_ids: string[];
  }>;
  age_coverage_recommendation?: {
    age_band_label: string;
    title: string;
    detail: string;
    confirmed_count: number;
    recommended_count: number;
    optional_count: number;
    items: Array<{
      category: string;
      status: "confirmed" | "missing" | "optional_missing";
      title: string;
      detail: string;
      evidence_ids: string[];
    }>;
    source: {
      label: string;
      url: string;
      published_at: string;
      reliability: string;
      caveat: string;
    };
  } | null;
  coverage_amount_status?: {
    title: string;
    detail: string;
    confirmed_total_amount: number;
    confirmed_category_count: number;
    unconfirmed_coverage_count: number;
    items: Array<{
      category: string;
      amount: number;
      coverage_count: number;
      title: string;
      detail: string;
      evidence_ids: string[];
    }>;
  };
  claim_condition_checks?: Array<{
    kind: "fixed" | "indemnity" | "contract";
    title: string;
    detail: string;
    evidence_ids: string[];
  }>;
  policy_change_checks?: Array<{
    title: string;
    summary: string;
    user_impact: string;
    effective_from: string | null;
    applies_to: string;
    source: {
      label: string;
      url: string;
      published_at: string;
      reliability: string;
      caveat: string;
    };
  }>;
  baseline_notice: string;
  classifications: ClassificationAnalysis[];
  sources: Array<{
    policy_id?: string;
    insurer?: string;
    product_name?: string;
  }>;
  notices: string[];
  evidence?: AnalysisEvidence[];
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

export type AnalysisEvidence = {
  id?: string;
  label?: string;
  detail?: string;
  fact?: string;
  source_title?: string;
  publisher?: string;
  citation_label?: string;
  policy_id?: string;
  insurer?: string;
  product_name?: string;
  coverage_name?: string;
  amount?: number;
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
  basis?: "confirmed_fact" | "general_guidance" | "personal_context";
  requires_personal_context?: boolean;
  required_context?: string[];
  evidence_ids: string[];
};

export type AnalysisContextAnswer = {
  question: string;
  answer: string;
};

export type ClaimChannelLink = { label: string; url: string };

export type ClaimChannelBlock = {
  insurers: Array<{
    name: string;
    customer_center?: string | null;
    note?: string | null;
    links: ClaimChannelLink[];
  }>;
  indemnity?: {
    name: string;
    description?: string | null;
    call_center?: string | null;
    links: ClaimChannelLink[];
  } | null;
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
  suggestions?: string[];
  generation?: "llm" | "fallback";
  sections?: Array<{
    title: string;
    content: string;
    basis: "confirmed_fact" | "general_guidance";
  }>;
  claim_channels?: ClaimChannelBlock | null;
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
    문서세션ID: result.문서세션ID,
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
  personalContext: AnalysisContextAnswer[] = [],
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
      personal_context: personalContext,
    },
    signal,
  );
}

export type QaStreamEnd = {
  status: QaAnswer["status"] | "clarify";
  generation?: "llm" | "fallback";
  citations: QaAnswer["citations"];
  limitations: string[];
  suggestions?: string[];
  claim_channels?: ClaimChannelBlock | null;
};

type QaStreamHandlers = {
  onMeta?: (meta: { status: QaStreamEnd["status"] }) => void;
  onDelta: (text: string) => void;
  onEnd: (end: QaStreamEnd) => void;
};

export async function streamPortfolioQuestion(
  question: string,
  insuranceDocuments: AnalyzedInsurance[],
  history: ChatHistoryItem[],
  handlers: QaStreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const demographics = getPolicyDemographics(insuranceDocuments);
  const response = await fetch(`${API_BASE_URL}/qa/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question: normalizeQuestion(question),
      policies: toPolicies(insuranceDocuments),
      demographics,
      history: prepareChatHistory(history),
    }),
    signal,
  });
  if (!response.ok || !response.body) {
    throw new Error(`Request failed: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const dispatch = (raw: string) => {
    const line = raw.trim();
    if (!line.startsWith("data:")) return;
    let event: Record<string, unknown>;
    try {
      event = JSON.parse(line.slice(5).trim()) as Record<string, unknown>;
    } catch {
      return; // skip a malformed/keepalive frame rather than aborting the stream
    }
    if (event.type === "meta") {
      handlers.onMeta?.({ status: event.status as QaStreamEnd["status"] });
    } else if (event.type === "delta") {
      handlers.onDelta(String(event.text ?? ""));
    } else if (event.type === "end") {
      handlers.onEnd(event as unknown as QaStreamEnd);
    }
  };

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      dispatch(buffer.slice(0, boundary));
      buffer = buffer.slice(boundary + 2);
      boundary = buffer.indexOf("\n\n");
    }
  }
  if (buffer.trim()) dispatch(buffer);
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

export type PolicyDemographicsCandidate = {
  age: number;
  gender: string;
  lifeStage?: string;
};

// Shared scan over non-auto policies for usable (age, gender) info. Callers
// apply their own policy on top: getPolicyDemographics here takes the first
// match (best-effort, for Q&A context); deriveDemographics in
// use-portfolio-analysis.ts requires a single unambiguous match across all
// documents (for the counselor-view demographics that must not silently guess).
export function collectPolicyDemographicsCandidates(
  insuranceDocuments: AnalyzedInsurance[],
): PolicyDemographicsCandidate[] {
  const candidates: PolicyDemographicsCandidate[] = [];
  for (const document of insuranceDocuments) {
    if (isAutoInsurance(document.result)) continue;
    const info = document.result.기본정보?.피보험자정보;
    if (typeof info?.나이 === "number" && info.성별) {
      candidates.push({
        age: info.나이,
        gender: info.성별,
        lifeStage: info.생애단계,
      });
    }
  }
  return candidates;
}

function getPolicyDemographics(insuranceDocuments: AnalyzedInsurance[]) {
  const [first] = collectPolicyDemographicsCandidates(insuranceDocuments);
  if (!first) return { age: null, gender: "미상", source: "unknown" as const };
  return { age: first.age, gender: first.gender, source: "policy" as const };
}
