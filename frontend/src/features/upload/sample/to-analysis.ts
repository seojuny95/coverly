import type { SamplePortfolioSessionResponse } from "@/shared/api/contracts";
import {
  getInsuredPersonName,
  type InsuranceAnalysis,
} from "@/features/analysis/types";

export function sampleSessionToAnalysis(
  sample: SamplePortfolioSessionResponse,
): InsuranceAnalysis {
  const insuranceDocuments = sample.insuranceDocuments.map(
    ({ fileName, result }) => {
      const { documentId, ...policyResult } = result;
      return { id: documentId, fileName, result: policyResult };
    },
  );
  const insuredNames = new Set(
    insuranceDocuments.flatMap((document) => {
      const name = getInsuredPersonName(document);
      return name ? [name] : [];
    }),
  );

  return {
    generatedAt: new Date().toISOString(),
    portfolioKind: sample.portfolioKind,
    portfolioSessionToken: sample.portfolioSessionToken,
    portfolioSessionExpiresAt: sample.expiresAt,
    counselTurnsRemaining: sample.counselTurnsRemaining,
    insuranceDocuments,
    ...(insuredNames.size === 1 ? { selectedName: [...insuredNames][0] } : {}),
  };
}
