import type { AnalyzedInsurance } from "../insurance-analysis/insurance-analysis-store";
import { isDamageInsurance } from "./analysis-eligibility";

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
  damage_coverages?: Array<{
    insurance_type: string;
    policies: Array<{
      policy_id?: string;
      insurer?: string;
      product_name?: string;
      coverages: Array<{
        coverage_name: string;
        original_amount?: string;
        major_category?: string;
      }>;
    }>;
  }>;
  excluded_auto_policy_count: number;
  essential_coverage_check?: {
    items: EssentialCoverageItem[];
  };
  special_policy_analyses?: SpecialPolicyAnalysis[];
  claim_channels?: ClaimChannelBlock | null;
  premium?: {
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
  } | null;
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
  overview?: {
    generation: "llm";
    title: string;
    paragraphs: string[];
    takeaways: Array<{
      label: string;
      title: string;
      detail: string;
    }>;
  } | null;
};

export type EssentialCoverageItem = {
  kind: "death" | "cancer" | "cerebrovascular" | "ischemic_heart" | "indemnity";
  label: string;
  status: "well_prepared" | "needs_review" | "not_found";
  confirmed_amount: number | null;
  reference_min_amount: number | null;
  reference_max_amount: number | null;
  coverage_count: number;
  detail: string;
  matched_coverage_names: string[];
};

export type SpecialPolicyAnalysis = {
  kind: "auto" | "driver" | "travel" | "fire";
  label: string;
  policy_count: number;
  product_names: string[];
  confirmed_coverage_names: string[];
  overview: string;
  coverage_checks: Array<{
    label: string;
    status: "confirmed" | "not_found";
    detail: string;
    matched_coverage_names: string[];
  }>;
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

type PolicyDemographicsCandidate = {
  age: number;
  gender: string;
  lifeStage?: string;
};

// Shared scan over non-damage policies for usable (age, gender) info. Q&A takes
// the first match as best-effort context; portfolio summary stays deterministic.
function collectPolicyDemographicsCandidates(
  insuranceDocuments: AnalyzedInsurance[],
): PolicyDemographicsCandidate[] {
  const candidates: PolicyDemographicsCandidate[] = [];
  for (const document of insuranceDocuments) {
    if (isDamageInsurance(document.result)) continue;
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
