import { findDuplicatePolicyDocuments } from "../../analysis/policy-identity";
import {
  type AnalyzedInsurance,
  type InsuranceAnalysis,
  getInsuredPersonName,
} from "../../analysis/types";
import type { SuccessfulUploadBatch } from "./upload-batch";

type UploadAnalysisValidation =
  | {
      kind: "missing-insured-person";
      documents: AnalyzedInsurance[];
    }
  | {
      kind: "duplicate-policy";
      documents: AnalyzedInsurance[];
    }
  | { kind: "insured-person-mismatch" }
  | { kind: "complete"; selectedName: string }
  | { kind: "select-name"; selectedName: string };

type SelectedFileReference = { id: string; fileName: string };

export type UploadValidationResult =
  | {
      kind: "complete";
      analysis: InsuranceAnalysis;
      selectedName: string;
    }
  | {
      kind: "select-name";
      analysis: InsuranceAnalysis;
      selectedName: string;
    }
  | { kind: "duplicate-files"; files: SelectedFileReference[] }
  | { kind: "missing-insured-person"; files: SelectedFileReference[] }
  | { kind: "insured-person-mismatch"; expectedName: string };

export async function validateUploadResult({
  uploadBatch,
  existingDocuments,
  requiredInsuredPersonName,
}: {
  uploadBatch: SuccessfulUploadBatch;
  existingDocuments: AnalyzedInsurance[];
  requiredInsuredPersonName?: string;
}): Promise<UploadValidationResult> {
  const validation = validateAnalysis({
    analysis: uploadBatch.analysis,
    existingDocuments,
    requiredInsuredPersonName,
  });

  const selectedFilesForDocuments = (
    documents: InsuranceAnalysis["insuranceDocuments"],
  ) =>
    documents.flatMap((document) => {
      const selectedFileId = uploadBatch.selectedFileIdsByDocumentId.get(
        document.id,
      );
      return selectedFileId
        ? [{ id: selectedFileId, fileName: document.fileName }]
        : [];
    });

  switch (validation.kind) {
    case "missing-insured-person":
      await uploadBatch.rollbackUploadedDocuments();
      return {
        kind: "missing-insured-person",
        files: selectedFilesForDocuments(validation.documents),
      };
    case "duplicate-policy":
      await uploadBatch.rollbackUploadedDocuments();
      return {
        kind: "duplicate-files",
        files: selectedFilesForDocuments(validation.documents),
      };
    case "insured-person-mismatch":
      await uploadBatch.rollbackUploadedDocuments();
      return {
        kind: "insured-person-mismatch",
        expectedName: requiredInsuredPersonName!,
      };
    case "complete":
      return {
        kind: "complete",
        analysis: uploadBatch.analysis,
        selectedName: validation.selectedName,
      };
    case "select-name":
      return {
        kind: "select-name",
        analysis: uploadBatch.analysis,
        selectedName: validation.selectedName,
      };
  }
}

function validateAnalysis({
  analysis,
  existingDocuments,
  requiredInsuredPersonName,
}: {
  analysis: InsuranceAnalysis;
  existingDocuments: AnalyzedInsurance[];
  requiredInsuredPersonName?: string;
}): UploadAnalysisValidation {
  const missingInsuredPerson = analysis.insuranceDocuments.filter(
    (document) => !getInsuredPersonName(document),
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

  const names = [
    ...new Set(
      analysis.insuranceDocuments
        .map(getInsuredPersonName)
        .filter((name): name is string => Boolean(name)),
    ),
  ];
  if (requiredInsuredPersonName) {
    return names.length === 1 && names[0] === requiredInsuredPersonName
      ? { kind: "complete", selectedName: requiredInsuredPersonName }
      : { kind: "insured-person-mismatch" };
  }

  return names.length === 1
    ? { kind: "complete", selectedName: names[0] }
    : { kind: "select-name", selectedName: names[0] ?? "" };
}
