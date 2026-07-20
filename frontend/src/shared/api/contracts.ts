import type { components } from "./generated";

type Schemas = components["schemas"];

export type ApiErrorDetail = Schemas["ApiErrorDetail"];
export type ApiErrorResponse = Schemas["ApiErrorResponse"];
export type ApiErrorCode = Schemas["ApiErrorCode"];

export type PolicyParseResponse = Schemas["PolicyParseResponse"];
export type PolicySummary = Schemas["PolicySummary"];
export type PolicyClassification = NonNullable<PolicySummary["보험분류"]>;
export type PolicyCoverage = Schemas["Coverage"];
export type CoveragePeriod = Schemas["CoveragePeriod"];
export type PremiumSummary = Schemas["PremiumSummary"];
export type InsuredDemographics = Schemas["InsuredDemographics"];
export type VehicleInfo = Schemas["VehicleInfo"];

export type PortfolioSessionRequest = Schemas["PortfolioSessionRequest"];
export type PortfolioSessionDocumentsDeleteRequest =
  Schemas["PortfolioSessionDocumentsDeleteRequest"];
export type PortfolioSessionResponse = Schemas["PortfolioSessionResponse"];
export type CoverageTotal = Schemas["CoverageTotalItem"];
export type PortfolioCoverageSummary = Schemas["PortfolioCoverageSummary"];
export type PortfolioSummaryRequest = Schemas["PortfolioSummaryRequest"];
export type DeathBenefitGuideInput = Schemas["DeathBenefitGuideInput"];

export type ClaimChannelBlock = Schemas["ClaimChannelBlock"];
export type SpecialPolicyAnalysis = Schemas["SpecialPolicyAnalysis"];
export type ReferenceSource = Schemas["ReferenceSource"];
export type SourceReliability = ReferenceSource["reliability"];
export type EssentialCoverageItem = Schemas["EssentialCoverageItem"];
export type CoverageGroup = Schemas["CoverageGroup"];

export type CounselRequest = Schemas["CounselRequest"];
export type ChatHistoryItem = Schemas["CounselMessage"];
export type CounselStreamEvent =
  | Schemas["CounselMetaEvent"]
  | Schemas["CounselDeltaEvent"]
  | Schemas["CounselEndEvent"];
export type CounselMetaEvent = Schemas["CounselMetaEvent"];
