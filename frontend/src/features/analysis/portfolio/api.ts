import type { AnalyzedInsurance } from "../store";
import { apiResponseError, apiUrl } from "../../../shared/api/client";
import {
  QaStreamProtocolError,
  requireQaStreamEvent,
} from "../../../shared/api/qa-stream";
import type {
  ClaimChannelBlock,
  ChatHistoryItem,
  QaMetaEvent,
  QaRequest,
  QaStreamEvent,
  CoverageTotal,
  CoverageGroup,
  DeathBenefitGuideInput,
  EssentialCoverageItem,
  PortfolioOverview,
  PortfolioCoverageSummary,
  PortfolioSummaryRequest,
  ReferenceSource,
  SourceReliability,
  SpecialPolicyAnalysis,
} from "../../../shared/api/contracts";

export type PortfolioSummary = PortfolioCoverageSummary;
export type {
  ChatHistoryItem,
  ClaimChannelBlock,
  CoverageTotal,
  CoverageGroup,
  DeathBenefitGuideInput,
  EssentialCoverageItem,
  PortfolioOverview,
  ReferenceSource,
  SourceReliability,
  SpecialPolicyAnalysis,
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

async function postPortfolioOverview(
  body: PortfolioSummaryRequest,
  signal?: AbortSignal,
): Promise<PortfolioOverview> {
  const response = await fetch(apiUrl("/portfolio/overview"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok) {
    throw await apiResponseError(response, "총평 생성에 실패했어요.");
  }
  return (await response.json()) as PortfolioOverview;
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

export function requestPortfolioOverview(
  insuranceDocuments: AnalyzedInsurance[],
  deathBenefitContext: DeathBenefitGuideInput,
  portfolioSessionToken: string,
  signal?: AbortSignal,
) {
  const body = {
    ...portfolioSelection(insuranceDocuments, portfolioSessionToken),
    death_benefit_context: deathBenefitContext,
  } satisfies PortfolioSummaryRequest;
  return postPortfolioOverview(body, signal);
}

type QaStreamHandlers = {
  onMeta?: (meta: QaMetaEvent) => void;
  onDelta: (text: string) => void | Promise<void>;
  onEnd: () => void;
};

export async function streamPortfolioQuestion(
  question: string,
  history: ChatHistoryItem[],
  handlers: QaStreamHandlers,
  portfolioSessionToken: string,
  signal?: AbortSignal,
): Promise<void> {
  const body = {
    question,
    session_id: portfolioSessionToken,
    history,
  } satisfies QaRequest;
  const response = await fetch(apiUrl("/qa/stream"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok || !response.body) {
    throw await apiResponseError(response, "상담 요청에 실패했어요.");
  }
  if (!response.headers.get("content-type")?.includes("text/event-stream")) {
    throw new QaStreamProtocolError();
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  const protocol: { phase: "meta" | "answer" | "end" } = { phase: "meta" };

  const dispatch = async (frame: string) => {
    const data = frame
      .split(/\r?\n/)
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).trimStart())
      .join("\n");
    if (!data) return;

    let payload: unknown;
    try {
      payload = JSON.parse(data);
    } catch {
      throw new QaStreamProtocolError();
    }
    const event: QaStreamEvent = requireQaStreamEvent(payload);

    if (event.type === "meta") {
      if (protocol.phase !== "meta") throw new QaStreamProtocolError();
      protocol.phase = "answer";
      handlers.onMeta?.(event);
    } else if (event.type === "delta") {
      if (protocol.phase !== "answer") throw new QaStreamProtocolError();
      await handlers.onDelta(event.text);
    } else if (event.type === "end") {
      if (protocol.phase !== "answer") throw new QaStreamProtocolError();
      protocol.phase = "end";
      handlers.onEnd();
    }
  };

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let boundary = nextSseBoundary(buffer);
    while (boundary) {
      await dispatch(buffer.slice(0, boundary.index));
      buffer = buffer.slice(boundary.index + boundary.length);
      if (protocol.phase === "end") {
        await reader.cancel();
        return;
      }
      boundary = nextSseBoundary(buffer);
    }
  }
  buffer += decoder.decode();
  if (buffer.trim()) await dispatch(buffer);
  if (protocol.phase !== "end") throw new QaStreamProtocolError();
}

function nextSseBoundary(buffer: string): {
  index: number;
  length: number;
} | null {
  const match = /\r?\n\r?\n/.exec(buffer);
  return match ? { index: match.index, length: match[0].length } : null;
}
