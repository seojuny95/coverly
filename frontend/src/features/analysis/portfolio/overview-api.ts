import type { AnalyzedInsurance } from "../store";
import { apiResponseError, apiUrl } from "../../../shared/api/client";
import {
  PORTFOLIO_REQUEST_TIMEOUT_MS,
  requestWithDeadline,
} from "../../../shared/api/request";
import type { PortfolioSummaryRequest } from "../../../shared/api/contracts";
import { portfolioSelection } from "./session-selection";
import type { DeathBenefitGuideInput, PortfolioOverview } from "./types";

async function postPortfolioOverview(
  body: PortfolioSummaryRequest,
  signal?: AbortSignal,
): Promise<PortfolioOverview> {
  const response = await requestWithDeadline(
    apiUrl("/portfolio/overview"),
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
    {
      signal,
      timeoutMs: PORTFOLIO_REQUEST_TIMEOUT_MS,
      timeoutMessage: "총평 생성 시간이 초과됐어요. 잠시 후 다시 시도해주세요.",
    },
  );
  if (!response.ok) {
    throw await apiResponseError(response, "총평 생성에 실패했어요.");
  }
  return (await response.json()) as PortfolioOverview;
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
