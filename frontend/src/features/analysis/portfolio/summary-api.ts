import type { AnalyzedInsurance } from "../store";
import { apiResponseError, apiUrl } from "../../../shared/api/client";
import {
  PORTFOLIO_REQUEST_TIMEOUT_MS,
  requestWithDeadline,
} from "../../../shared/api/request";
import { retryOperation } from "../../../shared/api/retry";
import type { PortfolioSummaryRequest } from "../../../shared/api/contracts";
import { portfolioSelection } from "./session-selection";
import type { DeathBenefitGuideInput, PortfolioSummary } from "./types";

async function postPortfolioSummary(
  body: PortfolioSummaryRequest,
  signal?: AbortSignal,
): Promise<PortfolioSummary> {
  return retryOperation(
    async () => {
      const response = await requestWithDeadline(
        apiUrl("/portfolio/summary"),
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
        {
          signal,
          timeoutMs: PORTFOLIO_REQUEST_TIMEOUT_MS,
          timeoutMessage:
            "분석 요청 시간이 초과됐어요. 잠시 후 다시 시도해주세요.",
        },
      );
      if (!response.ok) {
        throw await apiResponseError(response, "분석 요청에 실패했어요.");
      }
      return (await response.json()) as PortfolioSummary;
    },
    { maxAttempts: 2, signal },
  );
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
