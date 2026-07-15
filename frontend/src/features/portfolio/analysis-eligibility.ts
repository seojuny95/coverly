import type { AnalyzedInsurance } from "../insurance-analysis/insurance-analysis-store";
import type { InsuranceUploadResult } from "../insurance-upload/upload-insurance";

// A document is analyzable when it carries at least one real 담보 row.
// "부가" rows are name-only rider/rate lines and are not analyzable content.
export function hasAnalyzableCoverage(result: InsuranceUploadResult): boolean {
  const coverages = result.보장목록 ?? [];
  return coverages.some((coverage) => coverage.유형 !== "부가");
}

export function isDamageInsurance(result: InsuranceUploadResult): boolean {
  const classification = result.기본정보?.보험분류;
  return (
    classification === "손해보험" ||
    classification === "자동차" ||
    classification === "자동차보험" ||
    classification === "운전자보험" ||
    classification === "운전자상해보험" ||
    classification === "배상·화재·기타"
  );
}

export function isAutoInsurance(result: InsuranceUploadResult): boolean {
  const classification = result.기본정보?.보험분류;
  return (
    classification === "자동차" ||
    classification === "자동차보험" ||
    Boolean(result.기본정보?.상품태그?.includes("자동차보험"))
  );
}

// Damage insurance is handled separately from the life/third-insurance analysis.
export function isAnalyzableDocument(document: AnalyzedInsurance): boolean {
  return (
    !isDamageInsurance(document.result) &&
    hasAnalyzableCoverage(document.result)
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
