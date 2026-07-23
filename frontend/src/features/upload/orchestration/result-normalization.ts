import type { AnalyzedInsurance } from "../../analysis/store";
import type { InsurancePolicyResult, UploadInsuranceError } from "../api";

export type FulfilledUploadResult = {
  status: "fulfilled";
  selectedFileId: string;
  documentId: string;
  fileName: string;
  policyResult: InsurancePolicyResult;
};

export type RejectedUploadResult = {
  status: "rejected";
  fileName: string;
  error: unknown;
  uploadError?: UploadInsuranceError;
};

export type UploadResult = FulfilledUploadResult | RejectedUploadResult;

export function normalizeSuccessfulUploadResults({
  uploadResults,
  fileFingerprints,
}: {
  uploadResults: UploadResult[];
  fileFingerprints: string[];
}) {
  const insuranceDocuments: AnalyzedInsurance[] = [];
  const selectedFileIdsByDocumentId = new Map<string, string>();

  for (const [index, result] of uploadResults.entries()) {
    if (result.status !== "fulfilled") continue;

    insuranceDocuments.push({
      id: result.documentId,
      fileName: result.fileName,
      fileFingerprint: fileFingerprints[index],
      result: result.policyResult,
    });
    selectedFileIdsByDocumentId.set(result.documentId, result.selectedFileId);
  }

  return { insuranceDocuments, selectedFileIdsByDocumentId };
}
