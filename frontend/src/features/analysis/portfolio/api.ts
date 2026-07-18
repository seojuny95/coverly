import type { AnalyzedInsurance } from "../store";
import { apiResponseError, apiUrl } from "../../../shared/api/client";
import type {
  ClaimChannelBlock,
  ChatHistoryItem,
  CoverageTotal,
  CoverageGroup,
  DeathBenefitGuideInput,
  EssentialCoverageItem,
  InsuredDemographics,
  PortfolioCoverageSummary,
  PortfolioQuestionRequest,
  PortfolioSummaryRequest,
  ReferenceSource,
  SourceReliability,
  SpecialPolicyAnalysis,
} from "../../../shared/api/contracts";
import { isDamageInsurance } from "./eligibility";

export type PortfolioSummary = PortfolioCoverageSummary;
export type {
  ChatHistoryItem,
  ClaimChannelBlock,
  CoverageTotal,
  CoverageGroup,
  DeathBenefitGuideInput,
  EssentialCoverageItem,
  ReferenceSource,
  SourceReliability,
  SpecialPolicyAnalysis,
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

async function postPortfolioSummary(
  body: PortfolioSummaryRequest,
  signal?: AbortSignal,
): Promise<PortfolioSummary> {
  const response = await fetch(apiUrl("/portfolio/summary"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok) {
    throw await apiResponseError(response, "분석 요청에 실패했어요.");
  }
  return (await response.json()) as PortfolioSummary;
}

function portfolioSelection(
  insuranceDocuments: AnalyzedInsurance[],
  portfolioSessionToken: string,
) {
  return {
    portfolioSessionToken,
    policyIds: insuranceDocuments.map((document) => document.id),
  };
}

export function requestPortfolioSummary(
  insuranceDocuments: AnalyzedInsurance[],
  deathBenefitContext: DeathBenefitGuideInput,
  portfolioSessionToken: string,
  signal?: AbortSignal,
) {
  const body = {
    ...portfolioSelection(insuranceDocuments, portfolioSessionToken),
    death_benefit_context: deathBenefitContext,
  } satisfies PortfolioSummaryRequest;
  return postPortfolioSummary(body, signal);
}

export type QaStreamEnd = {
  status: QaAnswer["status"] | "clarify";
  generation?: "llm" | "fallback";
  citations: QaAnswer["citations"];
  limitations: string[];
  suggestions?: string[];
  claim_channels?: ClaimChannelBlock | null;
};

export type QaStreamProgress = {
  stage: string;
  text: string;
};

type QaStreamHandlers = {
  onMeta?: (meta: { status: QaStreamEnd["status"] }) => void;
  onProgress?: (progress: QaStreamProgress) => void;
  onDelta: (text: string) => void | Promise<void>;
  onEnd: (end: QaStreamEnd) => void;
};

export async function streamPortfolioQuestion(
  question: string,
  insuranceDocuments: AnalyzedInsurance[],
  history: ChatHistoryItem[],
  handlers: QaStreamHandlers,
  portfolioSessionToken: string,
  signal?: AbortSignal,
): Promise<void> {
  const demographics = getPolicyDemographics(insuranceDocuments);
  const body = {
    question,
    ...portfolioSelection(insuranceDocuments, portfolioSessionToken),
    demographics,
    history: prepareChatHistory(history),
  } satisfies PortfolioQuestionRequest;
  const response = await fetch(apiUrl("/qa/stream"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok || !response.body) {
    throw await apiResponseError(response, "상담 요청에 실패했어요.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const dispatch = async (raw: string) => {
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
    } else if (event.type === "progress") {
      handlers.onProgress?.({
        stage: String(event.stage ?? ""),
        text: String(event.text ?? ""),
      });
    } else if (event.type === "delta") {
      await handlers.onDelta(String(event.text ?? ""));
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
      await dispatch(buffer.slice(0, boundary));
      buffer = buffer.slice(boundary + 2);
      boundary = buffer.indexOf("\n\n");
    }
  }
  if (buffer.trim()) await dispatch(buffer);
}

export function prepareChatHistory(history: ChatHistoryItem[]) {
  return history.slice(-12);
}

export type PolicyDemographicsCandidate = {
  age: number;
  gender: InsuredDemographics["성별"];
  lifeStage?: InsuredDemographics["생애단계"];
};

// Shared scan over non-damage policies for usable (age, gender) info. Q&A takes
// the first match as best-effort context; portfolio summary stays deterministic.
export function collectPolicyDemographicsCandidates(
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
  if (!first) {
    return {
      age: null,
      gender: "미상" as const,
      source: "unknown" as const,
      status: "missing" as const,
    };
  }
  return {
    age: first.age,
    gender: first.gender,
    source: "policy" as const,
    status: "verified_policy" as const,
  };
}
