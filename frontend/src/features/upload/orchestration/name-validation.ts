import {
  findByteIdenticalDuplicateIndexes,
  findDuplicatePolicyDocuments,
} from "../../analysis/policy-identity";
import {
  type AnalyzedInsurance,
  type InsuranceAnalysis,
  getInsuredPersonName,
} from "../../analysis/store";
import type { SelectedUploadFile } from "../types";
import { getInsuranceNameOptions } from "./name-options";

export type UploadAnalysisValidation =
  | {
      kind: "missing-insured-person";
      documents: AnalyzedInsurance[];
    }
  | {
      kind: "duplicate-policy";
      documents: AnalyzedInsurance[];
    }
  | {
      kind: "byte-identical-duplicate";
      selectedFiles: SelectedUploadFile[];
    }
  | { kind: "fixed-name-mismatch" }
  | { kind: "complete"; selectedName: string }
  | { kind: "select-name"; selectedName: string };

export function validateUploadedAnalysis({
  analysis,
  selectedUploadFiles,
  fileFingerprints,
  existingDocuments,
  fixedSelectedName,
}: {
  analysis: InsuranceAnalysis;
  selectedUploadFiles: SelectedUploadFile[];
  fileFingerprints: string[];
  existingDocuments: AnalyzedInsurance[];
  fixedSelectedName?: string;
}): UploadAnalysisValidation {
  const byteIdenticalIndexes = findByteIdenticalDuplicateIndexes({
    fingerprints: fileFingerprints,
    existingDocuments,
  });
  if (byteIdenticalIndexes.size > 0) {
    return {
      kind: "byte-identical-duplicate",
      selectedFiles: selectedUploadFiles.filter((_, index) =>
        byteIdenticalIndexes.has(index),
      ),
    };
  }

  const missingInsuredPerson = analysis.insuranceDocuments.filter(
    (insuranceDocument) => !getInsuredPersonName(insuranceDocument),
  );
  if (missingInsuredPerson.length > 0) {
    return { kind: "missing-insured-person", documents: missingInsuredPerson };
  }

  const duplicateDocuments = findDuplicatePolicyDocuments({
    candidates: analysis.insuranceDocuments,
    existingDocuments,
  });
  if (duplicateDocuments.length > 0) {
    return { kind: "duplicate-policy", documents: duplicateDocuments };
  }

  const names = getInsuranceNameOptions(analysis.insuranceDocuments).map(
    (option) => option.name,
  );
  if (fixedSelectedName) {
    return names.length === 1 && names[0] === fixedSelectedName
      ? { kind: "complete", selectedName: fixedSelectedName }
      : { kind: "fixed-name-mismatch" };
  }

  return names.length === 1
    ? { kind: "complete", selectedName: names[0] }
    : { kind: "select-name", selectedName: names[0] ?? "" };
}
