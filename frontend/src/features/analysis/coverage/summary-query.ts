import { queryOptions } from "@tanstack/react-query";

import { reportClientOperationFailure } from "@/shared/api/errors";
import type { AnalyzedInsurance } from "../session/store";
import { isExpiredSessionError } from "../session/errors";
import { requestPortfolioSummary } from "./api";
import type { DeathBenefitGuideInput } from "./types";
import { portfolioSummaryQueryKey } from "./query-key";

export function portfolioSummaryQueryOptions({
  documents,
  deathBenefitContext,
  portfolioSessionToken,
  onSessionExpired,
}: {
  documents: AnalyzedInsurance[];
  deathBenefitContext: DeathBenefitGuideInput;
  portfolioSessionToken: string;
  onSessionExpired?: () => void;
}) {
  return queryOptions({
    queryKey: portfolioSummaryQueryKey(documents, deathBenefitContext),
    queryFn: ({ signal }) =>
      requestPortfolioSummary(
        documents,
        deathBenefitContext,
        portfolioSessionToken,
        signal,
      ).catch((error: unknown) => {
        if (isExpiredSessionError(error)) onSessionExpired?.();
        if (!(error instanceof Error && error.name === "AbortError")) {
          reportClientOperationFailure("portfolio_summary", error);
        }
        throw error;
      }),
  });
}
