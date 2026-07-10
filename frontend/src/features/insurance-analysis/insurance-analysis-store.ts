import type { InsuranceUploadResult } from "../insurance-upload/upload-insurance";

const STORAGE_KEY = "coverly.insuranceAnalysis";
const LEGACY_STORAGE_KEY = "coverly.policyAnalysis";

export type AnalyzedInsurance = {
  id: string;
  fileName: string;
  result: InsuranceUploadResult;
};

export type InsuranceAnalysis = {
  generatedAt: string;
  selectedName?: string;
  insuranceDocuments: AnalyzedInsurance[];
};

type StoredInsuranceAnalysis = Partial<InsuranceAnalysis> & {
  policies?: unknown[];
};

export function saveInsuranceAnalysis(analysis: InsuranceAnalysis) {
  window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(analysis));
  window.sessionStorage.removeItem(LEGACY_STORAGE_KEY);
}

export function loadInsuranceAnalysis(): InsuranceAnalysis | null {
  const rawAnalysis =
    window.sessionStorage.getItem(STORAGE_KEY) ??
    window.sessionStorage.getItem(LEGACY_STORAGE_KEY);
  if (!rawAnalysis) return null;

  try {
    const parsed = JSON.parse(rawAnalysis) as StoredInsuranceAnalysis;
    const insuranceDocuments = Array.isArray(parsed.insuranceDocuments)
      ? parsed.insuranceDocuments
      : Array.isArray(parsed.policies)
        ? parsed.policies
        : null;
    if (!parsed.generatedAt || !insuranceDocuments) return null;

    return {
      generatedAt: parsed.generatedAt,
      selectedName:
        typeof parsed.selectedName === "string"
          ? parsed.selectedName
          : undefined,
      insuranceDocuments: insuranceDocuments.filter(isAnalyzedInsurance),
    };
  } catch {
    return null;
  }
}

function isAnalyzedInsurance(value: unknown): value is AnalyzedInsurance {
  if (!value || typeof value !== "object") return false;

  const candidate = value as Partial<AnalyzedInsurance>;
  return (
    typeof candidate.id === "string" &&
    typeof candidate.fileName === "string" &&
    Boolean(candidate.result)
  );
}

export function getInsuredPersonName(
  insuranceDocument: AnalyzedInsurance,
): string | null {
  const insuredName = insuranceDocument.result.기본정보?.피보험자?.trim();
  if (insuredName) return insuredName;

  return null;
}
