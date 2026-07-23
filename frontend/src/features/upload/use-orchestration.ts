"use client";

import { useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";
import {
  type AnalyzedInsurance,
  type InsuranceAnalysis,
  getInsuredPersonName,
  useInsuranceData,
} from "../analysis/store";
import {
  deletePortfolioSessionDocuments,
  type PortfolioSessionResult,
} from "../analysis/session-api";
import {
  findByteIdenticalDuplicateIndexes,
  findDuplicatePolicyDocuments,
} from "../analysis/policy-identity";
import { UploadInsuranceError } from "./api";
import type { SelectedUploadFile, UploadInsurance } from "./types";
import { useCompletionBeat } from "./use-completion-beat";
import { useSelectedFiles } from "./use-selected-files";
import { useUploadCleanup } from "./use-upload-cleanup";
import {
  ROLLBACK_ERROR_MESSAGE,
  UploadRollbackError,
  isExpiredUploadSessionError,
  isFileSpecificUploadError,
  messageForFailedUploads,
  messageForSubmitFailure,
} from "./upload-helpers";

export function getInsuranceNameOptions(
  insuranceDocuments: AnalyzedInsurance[],
) {
  const counts = new Map<string, number>();
  for (const insuranceDocument of insuranceDocuments) {
    const personName = getInsuredPersonName(insuranceDocument);
    if (!personName) continue;
    counts.set(personName, (counts.get(personName) ?? 0) + 1);
  }

  return Array.from(counts.entries()).map(([name, count]) => ({
    name,
    count,
  }));
}

// Coordinates the upload lifecycle: file selection, byte-dedup, parallel upload
// with per-file progress, post-parse duplicate + insured-name resolution, and
// error/degrade handling. The server owns PDF validation.
export function useUploadOrchestration({
  uploadInsurance,
  onAnalysisComplete,
  navigateToAnalysis,
  fixedSelectedName,
  existingDocuments,
  createSession,
  deleteSessionDocuments = deletePortfolioSessionDocuments,
}: {
  uploadInsurance: UploadInsurance;
  onAnalysisComplete?: (analysis: InsuranceAnalysis) => void;
  navigateToAnalysis: () => void;
  fixedSelectedName?: string;
  existingDocuments: AnalyzedInsurance[];
  createSession: () => Promise<PortfolioSessionResult>;
  deleteSessionDocuments?: (
    portfolioSessionToken: string,
    documentIds: string[],
  ) => Promise<void>;
}) {
  const {
    analysis: currentAnalysis,
    setAnalysis,
    expireSession,
  } = useInsuranceData();
  const router = useRouter();
  const uploadMutation = useMutation({ mutationFn: uploadInsurance });
  const sessionMutation = useMutation({
    mutationFn: createSession,
  });

  // This route is reached programmatically after a long-running upload, so it
  // does not get Link's automatic prefetch. Prepare it while the user selects
  // files to keep the completed loading screen continuous with the result.
  useEffect(() => {
    router.prefetch("/analysis");
  }, [router]);

  const completeAnalysis =
    onAnalysisComplete ??
    ((analysis: InsuranceAnalysis) => {
      setAnalysis(analysis);
      router.push("/analysis");
    });
  const { isCompleting, runAfterBeat } = useCompletionBeat();
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisProgress, setAnalysisProgress] = useState({
    completed: 0,
    total: 0,
  });
  const [pendingAnalysis, setPendingAnalysis] =
    useState<InsuranceAnalysis | null>(null);
  const [selectedName, setSelectedName] = useState("");
  const { resolvePendingCleanup, rollbackSessionDocuments } = useUploadCleanup(
    deleteSessionDocuments,
  );

  const {
    selectedUploadFiles,
    setSelectedUploadFiles,
    isCheckingPasswords,
    error,
    setError,
    inputRef,
    selectFiles,
    removeSelectedFile,
    updateSelectedFilePassword,
    failSelectedFiles,
    rejectDuplicateFiles,
    markSelectedFilesReading,
    resetReadingFilesToIdle,
    fingerprintSelectedFiles,
  } = useSelectedFiles({
    isLocked: Boolean(pendingAnalysis) || isAnalyzing,
    onSelectionReset: () => {
      setPendingAnalysis(null);
      setSelectedName("");
    },
  });

  // Retry a cleanup a previous failed submit left pending, before starting a
  // new upload. Returns false when the cleanup still fails and submit must abort.
  const preparePendingCleanup = async () => {
    setIsAnalyzing(true);
    setError(null);
    if (await resolvePendingCleanup()) {
      return true;
    }
    setError(ROLLBACK_ERROR_MESSAGE);
    setIsAnalyzing(false);
    return false;
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (
      selectedUploadFiles.length === 0 ||
      isAnalyzing ||
      pendingAnalysis ||
      isCheckingPasswords
    )
      return;

    if (!(await preparePendingCleanup())) return;

    setIsAnalyzing(true);
    setAnalysisProgress({ completed: 0, total: selectedUploadFiles.length });
    markSelectedFilesReading();
    setError(null);
    setPendingAnalysis(null);
    setSelectedName("");
    let shouldKeepProgress = false;
    let portfolioSessionToken: string | undefined;
    const assignedDocumentIds = new Map(
      selectedUploadFiles.map((selectedFile) => [
        selectedFile.id,
        crypto.randomUUID(),
      ]),
    );
    let successfulDocumentIds: string[] = [];
    const rollbackDocuments = async (documentIds: string[]) => {
      const rolledBackDocumentIds = await rollbackSessionDocuments(
        portfolioSessionToken,
        documentIds,
      );
      successfulDocumentIds = successfulDocumentIds.filter(
        (documentId) => !rolledBackDocumentIds.includes(documentId),
      );
    };
    const rollbackSuccessfulDocuments = () =>
      rollbackDocuments(successfulDocumentIds);
    try {
      const portfolioSession = currentAnalysis
        ? {
            portfolioSessionToken: currentAnalysis.portfolioSessionToken,
            expiresAt: currentAnalysis.portfolioSessionExpiresAt,
            // Adding a policy must not hand back question turns already spent.
            counselTurnsRemaining: currentAnalysis.counselTurnsRemaining,
          }
        : await sessionMutation.mutateAsync();
      portfolioSessionToken = portfolioSession.portfolioSessionToken;

      // Upload one selected file, advancing the shared progress counter and its
      // per-file status for both success and failure.
      const uploadSelectedFile = async (selectedFile: SelectedUploadFile) => {
        try {
          const uploadInput = {
            file: selectedFile.file,
            documentId: assignedDocumentIds.get(selectedFile.id)!,
            ...(selectedFile.password
              ? { password: selectedFile.password }
              : {}),
            portfolioSessionToken: portfolioSession.portfolioSessionToken,
          };
          const result = await uploadMutation.mutateAsync(uploadInput);
          successfulDocumentIds = [
            ...successfulDocumentIds,
            uploadInput.documentId,
          ];
          const { documentId: _documentId, ...policyResult } = result;
          void _documentId;
          setAnalysisProgress((current) => ({
            ...current,
            completed: current.completed + 1,
          }));
          setSelectedUploadFiles((current) =>
            current.map((currentFile) =>
              currentFile.id === selectedFile.id
                ? { ...currentFile, status: "done" }
                : currentFile,
            ),
          );
          return {
            status: "fulfilled" as const,
            selectedFileId: selectedFile.id,
            documentId: uploadInput.documentId,
            fileName: selectedFile.file.name,
            policyResult,
          };
        } catch (err) {
          const uploadError = isFileSpecificUploadError(err)
            ? (err as UploadInsuranceError)
            : undefined;
          setAnalysisProgress((current) => ({
            ...current,
            completed: current.completed + 1,
          }));
          setSelectedUploadFiles((current) =>
            current.map((currentFile) =>
              currentFile.id === selectedFile.id
                ? uploadError
                  ? {
                      ...currentFile,
                      status: "failed",
                      errorCode: uploadError.code,
                      errorMessage: uploadError.userMessage,
                    }
                  : { ...currentFile, status: "idle" }
                : currentFile,
            ),
          );
          return {
            status: "rejected" as const,
            fileName: selectedFile.file.name,
            error: err,
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
        if (expiredSessionFailure) {
          expireSession();
          throw expiredSessionFailure.error;
        }
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
        await rollbackSuccessfulDocuments();
        const uploadErrors = failedUploads.flatMap((result) =>
          result.uploadError ? [result.uploadError] : [],
        );
        setError(messageForFailedUploads(uploadErrors));
        return;
      }

      const fileFingerprints =
        await fingerprintSelectedFiles(selectedUploadFiles);
      const byteIdenticalIndexes = findByteIdenticalDuplicateIndexes({
        fingerprints: fileFingerprints,
        existingDocuments,
      });
      if (byteIdenticalIndexes.size > 0) {
        await rollbackSuccessfulDocuments();
        rejectDuplicateFiles(
          selectedUploadFiles
            .filter((_, index) => byteIdenticalIndexes.has(index))
            .map((selectedFile) => ({
              id: selectedFile.id,
              fileName: selectedFile.file.name,
            })),
        );
        return;
      }

      const insuranceDocuments = uploadResults.flatMap((result, index) =>
        result.status === "fulfilled"
          ? [
              {
                id: result.documentId,
                fileName: result.fileName,
                fileFingerprint: fileFingerprints[index],
                result: result.policyResult,
              },
            ]
          : [],
      );
      const selectedFileIdsByDocumentId = new Map(
        uploadResults.flatMap((result) =>
          result.status === "fulfilled"
            ? [[result.documentId, result.selectedFileId]]
            : [],
        ),
      );
      const analysis = {
        generatedAt: new Date().toISOString(),
        portfolioSessionToken: portfolioSession.portfolioSessionToken,
        portfolioSessionExpiresAt: portfolioSession.expiresAt,
        counselTurnsRemaining: portfolioSession.counselTurnsRemaining,
        insuranceDocuments,
      };
      shouldKeepProgress = await continueWithNameValidation(
        analysis,
        selectedFileIdsByDocumentId,
        rollbackSuccessfulDocuments,
      );
    } catch (err) {
      const expiredSessionError = isExpiredUploadSessionError(err);
      if (expiredSessionError) {
        expireSession();
      }
      if (
        !expiredSessionError &&
        !(err instanceof UploadRollbackError) &&
        successfulDocumentIds.length > 0
      ) {
        try {
          await rollbackSuccessfulDocuments();
        } catch {
          err = new UploadRollbackError();
        }
      }
      resetReadingFilesToIdle();
      setError(messageForSubmitFailure(err));
    } finally {
      if (!shouldKeepProgress) {
        setIsAnalyzing(false);
      }
    }
  };

  const continueWithNameValidation = async (
    analysis: InsuranceAnalysis,
    selectedFileIdsByDocumentId: Map<string, string>,
    rollbackSuccessfulDocuments: () => Promise<void>,
  ) => {
    const insuranceDocumentsWithoutName = analysis.insuranceDocuments.filter(
      (insuranceDocument) => !getInsuredPersonName(insuranceDocument),
    );
    if (insuranceDocumentsWithoutName.length > 0) {
      await rollbackSuccessfulDocuments();
      failSelectedFiles(
        insuranceDocumentsWithoutName.flatMap((document) => {
          const selectedFileId = selectedFileIdsByDocumentId.get(document.id);
          return selectedFileId
            ? [{ id: selectedFileId, fileName: document.fileName }]
            : [];
        }),
        "MISSING_INSURED_PERSON",
        "피보험자를 확인할 수 없는 증권이에요.",
      );
      return false;
    }

    const duplicateDocuments = findDuplicatePolicyDocuments({
      candidates: analysis.insuranceDocuments,
      existingDocuments,
    });
    if (duplicateDocuments.length > 0) {
      await rollbackSuccessfulDocuments();
      rejectDuplicateFiles(
        duplicateDocuments.flatMap((document) => {
          const selectedFileId = selectedFileIdsByDocumentId.get(document.id);
          return selectedFileId
            ? [{ id: selectedFileId, fileName: document.fileName }]
            : [];
        }),
      );
      return false;
    }

    if (fixedSelectedName) {
      const names = getInsuranceNameOptions(analysis.insuranceDocuments).map(
        (option) => option.name,
      );
      if (names.length > 1 || names[0] !== fixedSelectedName) {
        await rollbackSuccessfulDocuments();
        setError(
          `${fixedSelectedName}님의 보험증권만 추가할 수 있어요. 같은 피보험자의 증권만 선택해주세요.`,
        );
        return false;
      }

      saveSelectedNameAnalysis(analysis, fixedSelectedName);
      return true;
    }

    const names = getInsuranceNameOptions(analysis.insuranceDocuments).map(
      (option) => option.name,
    );
    if (names.length === 1) {
      saveSelectedNameAnalysis(analysis, names[0]);
      return true;
    }

    setSelectedName(names[0] ?? "");
    setPendingAnalysis(analysis);
    return false;
  };

  const saveSelectedNameAnalysis = (
    analysis: InsuranceAnalysis,
    personName: string,
  ) => {
    const filteredAnalysis = {
      ...analysis,
      selectedName: personName,
      insuranceDocuments: analysis.insuranceDocuments.filter(
        (insuranceDocument) =>
          getInsuredPersonName(insuranceDocument) === personName,
      ),
    };
    runAfterBeat(() => {
      completeAnalysis(filteredAnalysis);
      navigateToAnalysis();
    });
  };

  const handleNameSelectionSubmit = async () => {
    if (!pendingAnalysis || !selectedName || isAnalyzing) return;
    const excludedDocumentIds = pendingAnalysis.insuranceDocuments
      .filter(
        (insuranceDocument) =>
          getInsuredPersonName(insuranceDocument) !== selectedName,
      )
      .map((insuranceDocument) => insuranceDocument.id);
    setIsAnalyzing(true);
    setError(null);
    try {
      await deleteSessionDocuments(
        pendingAnalysis.portfolioSessionToken,
        excludedDocumentIds,
      );
      // No setIsAnalyzing(false) here: the progress screen must stay up through
      // the completion beat, or the name-selection panel flashes back.
      saveSelectedNameAnalysis(pendingAnalysis, selectedName);
    } catch {
      setError(ROLLBACK_ERROR_MESSAGE);
      setIsAnalyzing(false);
    }
  };

  return {
    selectedUploadFiles,
    isCheckingPasswords,
    isAnalyzing,
    isCompleting,
    analysisProgress,
    pendingAnalysis,
    selectedName,
    setSelectedName,
    error,
    inputRef,
    selectFiles,
    removeSelectedFile,
    updateSelectedFilePassword,
    handleSubmit,
    handleNameSelectionSubmit,
  };
}
