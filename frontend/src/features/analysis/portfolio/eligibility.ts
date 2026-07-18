import type { AnalyzedInsurance } from "../store";
import type { InsurancePolicyResult } from "../../upload/api";
import {
  isAutoClassification,
  isDamageClassification,
} from "../classification";

// A document is analyzable when it carries at least one real 담보 row.
// "부가" rows are name-only rider/rate lines and are not analyzable content.
export function hasAnalyzableCoverage(result: InsurancePolicyResult): boolean {
  const coverages = result.보장목록 ?? [];
  return coverages.some((coverage) => coverage.유형 !== "부가");
}

export function isDamageInsurance(result: InsurancePolicyResult): boolean {
  return isDamageClassification(result.기본정보?.보험분류);
}

export function isAutoInsurance(result: InsurancePolicyResult): boolean {
  return isAutoClassification(
    result.기본정보?.보험분류,
    result.기본정보?.상품태그,
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
