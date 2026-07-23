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
export type PortfolioOverview = Schemas["PortfolioOverview"];
export type PortfolioSummaryRequest = Schemas["PortfolioSummaryRequest"];
export type DeathBenefitGuideInput = Schemas["DeathBenefitGuideInput"];

export type ClaimChannelBlock = Schemas["ClaimChannelBlock"];
export type SpecialPolicyAnalysis = Schemas["SpecialPolicyAnalysis"];
export type ReferenceSource = Schemas["ReferenceSource"];
export type SourceReliability = ReferenceSource["reliability"];
export type EssentialCoverageItem = Schemas["EssentialCoverageItem"];
export type CoverageGroup = Schemas["CoverageGroup"];

export type QaRequest = Schemas["QaRequest"];
export type ChatHistoryItem = Schemas["QaMessage"];
export type QaStreamEvent =
  Schemas["QaMetaEvent"] | Schemas["QaDeltaEvent"] | Schemas["QaEndEvent"];
export type QaMetaEvent = Schemas["QaMetaEvent"];
