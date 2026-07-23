import type { AnalyzedInsurance } from "../store";

export function portfolioSelection(
  insuranceDocuments: AnalyzedInsurance[],
  portfolioSessionToken: string,
) {
  return {
    portfolioSessionToken,
    policyIds: insuranceDocuments.map((document) => document.id),
  };
}
