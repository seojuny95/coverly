import type {
  InsuranceAnalysis,
  PolicyAnalysisResult,
} from "../../analysis/types";
import type { PortfolioSessionResult } from "../../analysis/session-api";
import { PolicyUploadError } from "../api";
import type { SelectedPolicyFile, UploadPolicyDocument } from "../types";
import {
  UploadedDocumentCleanupError,
  isAbortError,
  isExpiredUploadSessionError,
  isFileSpecificUploadError,
} from "../errors";

type FulfilledUploadResult = {
  status: "fulfilled";
  selectedFileId: string;
  documentId: string;
  fileName: string;
  policyResult: PolicyAnalysisResult;
};

type RejectedUploadResult = {
  status: "rejected";
  fileName: string;
  error: unknown;
  uploadError?: PolicyUploadError;
};

type UploadResult = FulfilledUploadResult | RejectedUploadResult;

type RollbackSessionDocuments = (
  portfolioSessionToken: string | undefined,
  documentIds: string[],
) => Promise<string[]>;

export type SuccessfulUploadBatch = {
  kind: "success";
  analysis: InsuranceAnalysis;
  selectedFileIdsByDocumentId: Map<string, string>;
  rollbackUploadedDocuments: () => Promise<void>;
};

type FileErrorUploadBatch = {
  kind: "file-errors";
  uploadErrors: PolicyUploadError[];
};

export type UploadBatchResult = SuccessfulUploadBatch | FileErrorUploadBatch;

export type UploadBatchProgressEvent =
  | { type: "server-ready" }
  | { type: "file-succeeded"; selectedFileId: string }
  | {
      type: "file-rejected";
      selectedFileId: string;
      uploadError?: PolicyUploadError;
    };

export async function uploadPolicyBatch({
  input,
  services,
  onProgress,
}: {
  input: {
    selectedFiles: SelectedPolicyFile[];
    currentAnalysis: InsuranceAnalysis | null;
    fileFingerprints: string[];
    signal?: AbortSignal;
  };
  services: {
    prepareServer: (signal?: AbortSignal) => Promise<void>;
    createSession: (signal?: AbortSignal) => Promise<PortfolioSessionResult>;
    uploadPolicyDocument: UploadPolicyDocument;
    rollbackSessionDocuments: RollbackSessionDocuments;
  };
  onProgress: (event: UploadBatchProgressEvent) => void;
}): Promise<UploadBatchResult> {
  const { selectedFiles, currentAnalysis, fileFingerprints, signal } = input;
  const {
    prepareServer,
    createSession,
    uploadPolicyDocument,
    rollbackSessionDocuments,
  } = services;
  let portfolioSessionToken: string | undefined;
  let successfulDocumentIds: string[] = [];
  const assignedDocumentIds = new Map(
    selectedFiles.map((selectedFile) => [selectedFile.id, crypto.randomUUID()]),
  );
  const rollbackDocuments = async (documentIds: string[]) => {
    const rolledBackDocumentIds = await rollbackSessionDocuments(
      portfolioSessionToken,
      documentIds,
    );
    successfulDocumentIds = successfulDocumentIds.filter(
      (documentId) => !rolledBackDocumentIds.includes(documentId),
    );
  };
  const rollbackUploadedDocuments = () =>
    rollbackDocuments(successfulDocumentIds);

  try {
    await prepareServer(signal);
    onProgress({ type: "server-ready" });
    const portfolioSession = currentAnalysis
      ? {
          portfolioSessionToken: currentAnalysis.portfolioSessionToken,
          expiresAt: currentAnalysis.portfolioSessionExpiresAt,
          // Adding a policy must not hand back question turns already spent.
          counselTurnsRemaining: currentAnalysis.counselTurnsRemaining,
        }
      : await createSession(signal);
    portfolioSessionToken = portfolioSession.portfolioSessionToken;

    const uploadSelectedFile = async (
      selectedFile: SelectedPolicyFile,
    ): Promise<UploadResult> => {
      try {
        const uploadInput = {
          file: selectedFile.file,
          documentId: assignedDocumentIds.get(selectedFile.id)!,
          ...(selectedFile.password ? { password: selectedFile.password } : {}),
          portfolioSessionToken: portfolioSession.portfolioSessionToken,
          signal,
        };
        const result = await uploadPolicyDocument(uploadInput);
        successfulDocumentIds = [
          ...successfulDocumentIds,
          uploadInput.documentId,
        ];
        const { documentId: _documentId, ...policyResult } = result;
        void _documentId;
        onProgress({
          type: "file-succeeded",
          selectedFileId: selectedFile.id,
        });
        return {
          status: "fulfilled",
          selectedFileId: selectedFile.id,
          documentId: uploadInput.documentId,
          fileName: selectedFile.file.name,
          policyResult,
        };
      } catch (error) {
        const isCancelled = signal?.aborted || isAbortError(error);
        const uploadError = isFileSpecificUploadError(error)
          ? (error as PolicyUploadError)
          : undefined;
        if (!isCancelled) {
          onProgress({
            type: "file-rejected",
            selectedFileId: selectedFile.id,
            uploadError,
          });
        }
        return {
          status: "rejected",
          fileName: selectedFile.file.name,
          error,
          uploadError,
        };
      }
    };

    const uploadResults = await Promise.all(
      selectedFiles.map(uploadSelectedFile),
    );
    const failedUploads = uploadResults.filter(
      (result) => result.status === "rejected",
    );
    if (failedUploads.length > 0) {
      const expiredSessionFailure = failedUploads.find((result) =>
        isExpiredUploadSessionError(result.error),
      );
      if (expiredSessionFailure) throw expiredSessionFailure.error;

      const unexpectedFailure = failedUploads.find(
        (result) => !result.uploadError,
      );
      if (unexpectedFailure) {
        const rejectedDocumentIds = uploadResults.flatMap((result, index) =>
          result.status === "rejected"
            ? [assignedDocumentIds.get(selectedFiles[index].id)!]
            : [],
        );
        await rollbackDocuments([
          ...successfulDocumentIds,
          ...rejectedDocumentIds,
        ]);
        throw unexpectedFailure.error;
      }

      await rollbackUploadedDocuments();
      return {
        kind: "file-errors",
        uploadErrors: failedUploads.flatMap((result) =>
          result.uploadError ? [result.uploadError] : [],
        ),
      };
    }

    const { insuranceDocuments, selectedFileIdsByDocumentId } =
      buildAnalysisDocuments({
        uploadResults,
        fileFingerprints,
      });
    return {
      kind: "success",
      analysis: {
        generatedAt: new Date().toISOString(),
        portfolioSessionToken: portfolioSession.portfolioSessionToken,
        portfolioSessionExpiresAt: portfolioSession.expiresAt,
        counselTurnsRemaining: portfolioSession.counselTurnsRemaining,
        insuranceDocuments,
      },
      selectedFileIdsByDocumentId,
      rollbackUploadedDocuments,
    };
  } catch (error) {
    const expiredSessionError = isExpiredUploadSessionError(error);
    if (
      !expiredSessionError &&
      !(error instanceof UploadedDocumentCleanupError) &&
      successfulDocumentIds.length > 0
    ) {
      try {
        await rollbackUploadedDocuments();
      } catch {
        throw new UploadedDocumentCleanupError();
      }
    }
    throw error;
  }
}

function buildAnalysisDocuments({
  uploadResults,
  fileFingerprints,
}: {
  uploadResults: UploadResult[];
  fileFingerprints: string[];
}) {
  const insuranceDocuments: InsuranceAnalysis["insuranceDocuments"] = [];
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
