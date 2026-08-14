import type {
  CoveragePeriod,
  PolicyCoverage,
  PolicyParseResponse,
  PolicySummary,
  PremiumSummary,
} from "@/shared/api/contracts";

export type InsurancePeriod = CoveragePeriod;
export type InsurancePremium = PremiumSummary;
export type InsuranceBasicInfo = PolicySummary;
export type InsuranceCoverage = PolicyCoverage;
export type PolicyAnalysisResult = Omit<PolicyParseResponse, "documentId">;

export type AnalyzedInsurance = {
  id: string;
  fileName: string;
  fileFingerprint?: string;
  result: PolicyAnalysisResult;
};

export type InsuranceAnalysis = {
  generatedAt: string;
  selectedName?: string;
  portfolioSessionToken: string;
  portfolioSessionExpiresAt: string;
  counselTurnsRemaining: number;
  insuranceDocuments: AnalyzedInsurance[];
};

export function getInsuredPersonName(
  insuranceDocument: AnalyzedInsurance,
): string | null {
  return insuranceDocument.result.기본정보?.피보험자?.trim() || null;
}
