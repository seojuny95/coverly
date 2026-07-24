import type { InsuranceAnalysis } from "../../analysis/store";
import type { PortfolioSessionResult } from "../../analysis/session-api";
import { UploadInsuranceError } from "../api";
import type { SelectedUploadFile, UploadInsurance } from "../types";
import {
  UploadRollbackError,
  isExpiredUploadSessionError,
  isFileSpecificUploadError,
} from "../upload-helpers";
import {
  normalizeSuccessfulUploadResults,
  type UploadResult,
} from "./result-normalization";

type RollbackSessionDocuments = (
  portfolioSessionToken: string | undefined,
  documentIds: string[],
) => Promise<string[]>;

export type SuccessfulUploadTransaction = {
  kind: "success";
  analysis: InsuranceAnalysis;
  fileFingerprints: string[];
  selectedFileIdsByDocumentId: Map<string, string>;
  rollbackUploadedDocuments: () => Promise<void>;
};

type FileErrorUploadTransaction = {
  kind: "file-errors";
  uploadErrors: UploadInsuranceError[];
};

export type UploadTransactionResult =
  SuccessfulUploadTransaction | FileErrorUploadTransaction;

export async function runUploadTransaction({
  selectedUploadFiles,
  currentAnalysis,
  prepareServer,
  createSession,
  uploadInsurance,
  fileFingerprints,
  signal,
  rollbackSessionDocuments,
  onFileSettled,
  onServerReady,
  onFileSucceeded,
  onFileRejected,
}: {
  selectedUploadFiles: SelectedUploadFile[];
  currentAnalysis: InsuranceAnalysis | null;
  prepareServer: (signal?: AbortSignal) => Promise<void>;
  createSession: (signal?: AbortSignal) => Promise<PortfolioSessionResult>;
  uploadInsurance: UploadInsurance;
  fileFingerprints: string[];
  signal?: AbortSignal;
  rollbackSessionDocuments: RollbackSessionDocuments;
  onFileSettled: () => void;
  onServerReady: () => void;
  onFileSucceeded: (selectedFileId: string) => void;
  onFileRejected: (
    selectedFileId: string,
    uploadError: UploadInsuranceError | undefined,
  ) => void;
}): Promise<UploadTransactionResult> {
  let portfolioSessionToken: string | undefined;
  let successfulDocumentIds: string[] = [];
  const assignedDocumentIds = new Map(
    selectedUploadFiles.map((selectedFile) => [
      selectedFile.id,
      crypto.randomUUID(),
    ]),
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
    onServerReady();
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
      selectedFile: SelectedUploadFile,
    ): Promise<UploadResult> => {
      try {
        const uploadInput = {
          file: selectedFile.file,
          documentId: assignedDocumentIds.get(selectedFile.id)!,
          ...(selectedFile.password ? { password: selectedFile.password } : {}),
          portfolioSessionToken: portfolioSession.portfolioSessionToken,
          signal,
        };
        const result = await uploadInsurance(uploadInput);
        successfulDocumentIds = [
          ...successfulDocumentIds,
          uploadInput.documentId,
        ];
        const { documentId: _documentId, ...policyResult } = result;
        void _documentId;
        onFileSettled();
        onFileSucceeded(selectedFile.id);
        return {
          status: "fulfilled",
          selectedFileId: selectedFile.id,
          documentId: uploadInput.documentId,
          fileName: selectedFile.file.name,
          policyResult,
        };
      } catch (error) {
        const uploadError = isFileSpecificUploadError(error)
          ? (error as UploadInsuranceError)
          : undefined;
        onFileSettled();
        onFileRejected(selectedFile.id, uploadError);
        return {
          status: "rejected",
          fileName: selectedFile.file.name,
          error,
          uploadError,
        };
      }
    };

    const uploadResults = await Promise.all(
      selectedUploadFiles.map(uploadSelectedFile),
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
            ? [assignedDocumentIds.get(selectedUploadFiles[index].id)!]
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
      normalizeSuccessfulUploadResults({
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
      fileFingerprints,
      selectedFileIdsByDocumentId,
      rollbackUploadedDocuments,
    };
  } catch (error) {
    const expiredSessionError = isExpiredUploadSessionError(error);
    if (
      !expiredSessionError &&
      !(error instanceof UploadRollbackError) &&
      successfulDocumentIds.length > 0
    ) {
      try {
        await rollbackUploadedDocuments();
      } catch {
        throw new UploadRollbackError();
      }
    }
    throw error;
  }
}
