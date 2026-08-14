import { findByteIdenticalDuplicateIndexes } from "../../analysis/policy-identity";
import type {
  AnalyzedInsurance,
  InsuranceAnalysis,
} from "../../analysis/types";
import type { PortfolioSessionResult } from "../../analysis/session/api";
import type { PolicyUploadError } from "../api";
import { isAbortError, isExpiredUploadSessionError } from "../errors";
import type { SelectedPolicyFile, UploadPolicyDocument } from "../types";
import {
  validateUploadResult,
  type UploadValidationResult,
} from "./validate-upload";
import {
  uploadPolicyBatch,
  type UploadBatchProgressEvent,
} from "./upload-batch";

type SubmitPolicyUploadInput = {
  selectedFiles: SelectedPolicyFile[];
  currentAnalysis: InsuranceAnalysis | null;
  existingDocuments: AnalyzedInsurance[];
  requiredInsuredPersonName?: string;
  signal: AbortSignal;
};

type SubmitPolicyUploadServices = {
  prepareServer: (signal?: AbortSignal) => Promise<void>;
  createSession: (signal?: AbortSignal) => Promise<PortfolioSessionResult>;
  uploadPolicyDocument: UploadPolicyDocument;
  resolvePendingCleanup: (signal?: AbortSignal) => Promise<boolean>;
  rollbackSessionDocuments: (
    portfolioSessionToken: string | undefined,
    documentIds: string[],
  ) => Promise<string[]>;
};

export type SubmitPolicyUploadResult =
  | UploadValidationResult
  | { kind: "cleanup-failed" }
  | { kind: "fingerprint-failed"; error: unknown }
  | { kind: "file-errors"; uploadErrors: PolicyUploadError[] }
  | { kind: "cancelled" }
  | { kind: "failed"; error: unknown; sessionExpired: boolean };

export type SubmitPolicyUploadProgressEvent =
  { type: "upload-started" } | UploadBatchProgressEvent;

export async function submitPolicyUpload({
  input,
  services,
  onProgress,
}: {
  input: SubmitPolicyUploadInput;
  services: SubmitPolicyUploadServices;
  onProgress: (event: SubmitPolicyUploadProgressEvent) => void;
}): Promise<SubmitPolicyUploadResult> {
  if (!(await services.resolvePendingCleanup(input.signal))) {
    if (input.signal.aborted) return { kind: "cancelled" };
    return { kind: "cleanup-failed" };
  }

  let fileFingerprints: string[];
  try {
    fileFingerprints = await fingerprintFiles(input.selectedFiles);
  } catch (error) {
    return { kind: "fingerprint-failed", error };
  }

  const duplicateIndexes = findByteIdenticalDuplicateIndexes({
    fingerprints: fileFingerprints,
    existingDocuments: input.existingDocuments,
  });
  if (duplicateIndexes.size > 0) {
    return {
      kind: "duplicate-files",
      files: input.selectedFiles
        .filter((_, index) => duplicateIndexes.has(index))
        .map((selectedFile) => ({
          id: selectedFile.id,
          fileName: selectedFile.file.name,
        })),
    };
  }

  onProgress({ type: "upload-started" });
  try {
    const uploadBatch = await uploadPolicyBatch({
      input: {
        selectedFiles: input.selectedFiles,
        currentAnalysis: input.currentAnalysis,
        fileFingerprints,
        signal: input.signal,
      },
      services: {
        prepareServer: services.prepareServer,
        createSession: services.createSession,
        uploadPolicyDocument: services.uploadPolicyDocument,
        rollbackSessionDocuments: services.rollbackSessionDocuments,
      },
      onProgress,
    });
    if (uploadBatch.kind === "file-errors") {
      return uploadBatch;
    }

    return await validateUploadResult({
      uploadBatch,
      existingDocuments: input.existingDocuments,
      requiredInsuredPersonName: input.requiredInsuredPersonName,
    });
  } catch (error) {
    if (isAbortError(error)) return { kind: "cancelled" };
    return {
      kind: "failed",
      error,
      sessionExpired: isExpiredUploadSessionError(error),
    };
  }
}

async function fingerprintFiles(files: SelectedPolicyFile[]) {
  const fingerprints: string[] = [];
  for (const selectedFile of files) {
    const buffer = await selectedFile.file.arrayBuffer();
    const digest = await crypto.subtle.digest("SHA-256", buffer);
    fingerprints.push(
      Array.from(new Uint8Array(digest))
        .map((byte) => byte.toString(16).padStart(2, "0"))
        .join(""),
    );
  }
  return fingerprints;
}
