import type { AnalyzedInsurance } from "../insurance-analysis/insurance-analysis-store";
import type { InsuranceUploadResult } from "../insurance-upload/upload-insurance";

// A document is analyzable when it carries at least one real 담보 row.
// "부가" rows are name-only rider/rate lines and are not analyzable content.
export function hasAnalyzableCoverage(result: InsuranceUploadResult): boolean {
  const coverages = result.보장목록 ?? [];
  return coverages.some((coverage) => coverage.유형 !== "부가");
}

export function isAutoInsurance(result: InsuranceUploadResult): boolean {
  return Boolean(result.기본정보?.보험분류?.includes("자동차"));
}

// Auto exclusion is kept to stay consistent with the backend is_auto_policy.
export function isAnalyzableDocument(document: AnalyzedInsurance): boolean {
  return (
    !isAutoInsurance(document.result) && hasAnalyzableCoverage(document.result)
  );
}

export type EmptyReason = "auto-only" | "no-coverage" | "mixed";

// Pick the copy variant when documents exist but none is analyzable.
export function emptyReasonFor(documents: AnalyzedInsurance[]): EmptyReason {
  const allAuto = documents.every((document) =>
    isAutoInsurance(document.result),
  );
  if (allAuto) return "auto-only";
  const anyAuto = documents.some((document) =>
    isAutoInsurance(document.result),
  );
  return anyAuto ? "mixed" : "no-coverage";
}
