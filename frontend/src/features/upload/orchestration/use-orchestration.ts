"use client";

import { useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useReducer, useRef } from "react";
import {
  type AnalyzedInsurance,
  type InsuranceAnalysis,
  getInsuredPersonName,
  useInsuranceData,
} from "../../analysis/store";
import { findByteIdenticalDuplicateIndexes } from "../../analysis/policy-identity";
import {
  deletePortfolioSessionDocuments,
  type PortfolioSessionResult,
} from "../../analysis/session-api";
import { PORTFOLIO_MAX_DOCUMENTS } from "@/shared/api/generated-runtime";
import { reportClientOperationFailure } from "@/shared/api/errors";
import type { UploadInsurance } from "../types";
import { useCompletionBeat } from "../use-completion-beat";
import { useSelectedFiles } from "../use-selected-files";
import {
  ROLLBACK_ERROR_MESSAGE,
  isExpiredUploadSessionError,
  messageForFailedUploads,
  messageForSubmitFailure,
} from "../upload-helpers";
import { useUploadCleanup } from "./rollback";
import {
  initialUploadWorkflowState,
  isUploadInFlight,
  uploadWorkflowReducer,
} from "./state";
import { runUploadTransaction } from "./upload-transaction";
import { resolveUploadValidation } from "./validation-resolution";

export { getInsuranceNameOptions } from "./name-options";

type UploadOrchestrationProps = {
  uploadInsurance: UploadInsurance;
  onAnalysisComplete?: (analysis: InsuranceAnalysis) => void;
  navigateToAnalysis: () => void;
  fixedSelectedName?: string;
  existingDocuments: AnalyzedInsurance[];
  prepareServer: (signal?: AbortSignal) => Promise<void>;
  createSession: (signal?: AbortSignal) => Promise<PortfolioSessionResult>;
  deleteSessionDocuments?: (
    portfolioSessionToken: string,
    documentIds: string[],
  ) => Promise<void>;
};

export function useUploadOrchestration({
  uploadInsurance,
  onAnalysisComplete,
  navigateToAnalysis,
  fixedSelectedName,
  existingDocuments,
  prepareServer,
  createSession,
  deleteSessionDocuments = deletePortfolioSessionDocuments,
}: UploadOrchestrationProps) {
  const {
    analysis: currentAnalysis,
    setAnalysis,
    expireSession,
  } = useInsuranceData();
  const router = useRouter();
  const uploadMutation = useMutation({ mutationFn: uploadInsurance });
  const readinessMutation = useMutation({
    mutationFn: (signal?: AbortSignal) => prepareServer(signal),
  });
  const sessionMutation = useMutation({
    mutationFn: (signal?: AbortSignal) => createSession(signal),
  });
  const activeUploadController = useRef<AbortController | null>(null);
  const [workflow, dispatch] = useReducer(
    uploadWorkflowReducer,
    initialUploadWorkflowState,
  );
  const { isCompleting, runAfterBeat } = useCompletionBeat();
  const { resolvePendingCleanup, rollbackSessionDocuments } = useUploadCleanup(
    deleteSessionDocuments,
  );
  const isAnalyzing = isUploadInFlight(workflow);

  useEffect(() => {
    // This route is reached after a long-running upload, not through a Link.
    router.prefetch("/analysis");
  }, [router]);

  useEffect(
    () => () => {
      activeUploadController.current?.abort();
    },
    [],
  );

  const completeAnalysis =
    onAnalysisComplete ??
    ((analysis: InsuranceAnalysis) => {
      setAnalysis(analysis);
      router.push("/analysis");
    });
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
    isLocked: workflow.phase === "name-selection" || isAnalyzing,
    maxSelectableFiles: Math.max(
      0,
      PORTFOLIO_MAX_DOCUMENTS - existingDocuments.length,
    ),
    onSelectionReset: () => dispatch({ type: "reset" }),
  });

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
    dispatch({ type: "begin-completion" });
    runAfterBeat(() => {
      completeAnalysis(filteredAnalysis);
      navigateToAnalysis();
    });
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (
      selectedUploadFiles.length === 0 ||
      isAnalyzing ||
      workflow.phase === "name-selection" ||
      isCheckingPasswords
    )
      return;

    dispatch({ type: "start", total: selectedUploadFiles.length });
    setError(null);
    if (!(await resolvePendingCleanup())) {
      setError(ROLLBACK_ERROR_MESSAGE);
      dispatch({ type: "finish" });
      return;
    }

    let fileFingerprints: string[];
    try {
      fileFingerprints = await fingerprintSelectedFiles(selectedUploadFiles);
    } catch (error) {
      reportClientOperationFailure("policy_fingerprint", error);
      setError(
        "PDF 파일을 확인하지 못했어요. 파일을 다시 선택한 뒤 시도해주세요.",
      );
      dispatch({ type: "finish" });
      return;
    }
    const duplicateIndexes = findByteIdenticalDuplicateIndexes({
      fingerprints: fileFingerprints,
      existingDocuments,
    });
    if (duplicateIndexes.size > 0) {
      rejectDuplicateFiles(
        selectedUploadFiles
          .filter((_, index) => duplicateIndexes.has(index))
          .map((selectedFile) => ({
            id: selectedFile.id,
            fileName: selectedFile.file.name,
          })),
      );
      dispatch({ type: "finish" });
      return;
    }

    markSelectedFilesReading();
    activeUploadController.current?.abort();
    const uploadController = new AbortController();
    activeUploadController.current = uploadController;
    let outcome: "finished" | "retained" = "finished";
    try {
      const transaction = await runUploadTransaction({
        selectedUploadFiles,
        currentAnalysis,
        prepareServer: readinessMutation.mutateAsync,
        createSession: sessionMutation.mutateAsync,
        uploadInsurance: uploadMutation.mutateAsync,
        fileFingerprints,
        signal: uploadController.signal,
        rollbackSessionDocuments,
        onFileSettled: () => dispatch({ type: "uploaded" }),
        onServerReady: () => dispatch({ type: "server-ready" }),
        onFileSucceeded: (selectedFileId) =>
          setSelectedUploadFiles((current) =>
            current.map((file) =>
              file.id === selectedFileId ? { ...file, status: "done" } : file,
            ),
          ),
        onFileRejected: (selectedFileId, uploadError) =>
          setSelectedUploadFiles((current) =>
            current.map((file) =>
              file.id !== selectedFileId
                ? file
                : uploadError
                  ? {
                      ...file,
                      status: "failed",
                      errorCode: uploadError.code,
                      errorMessage: uploadError.userMessage,
                    }
                  : { ...file, status: "idle" },
            ),
          ),
      });
      if (transaction.kind === "file-errors") {
        setError(messageForFailedUploads(transaction.uploadErrors));
        return;
      }
      outcome = await resolveUploadValidation({
        transaction,
        selectedUploadFiles,
        existingDocuments,
        fixedSelectedName,
        failSelectedFiles,
        rejectDuplicateFiles,
        setError,
        onComplete: saveSelectedNameAnalysis,
        onSelectName: (analysis, selectedName) =>
          dispatch({
            type: "require-name-selection",
            analysis,
            selectedName,
          }),
      });
    } catch (error) {
      if (isExpiredUploadSessionError(error)) expireSession();
      reportClientOperationFailure("policy_upload", error);
      resetReadingFilesToIdle();
      setError(messageForSubmitFailure(error));
    } finally {
      if (activeUploadController.current === uploadController) {
        activeUploadController.current = null;
      }
      if (outcome === "finished") dispatch({ type: "finish" });
    }
  };

  const handleNameSelectionSubmit = async () => {
    if (workflow.phase !== "name-selection" || !workflow.selectedName) return;

    const { pendingAnalysis, selectedName } = workflow;
    const excludedDocumentIds = pendingAnalysis.insuranceDocuments
      .filter((document) => getInsuredPersonName(document) !== selectedName)
      .map((document) => document.id);
    dispatch({ type: "begin-completion" });
    setError(null);
    try {
      await deleteSessionDocuments(
        pendingAnalysis.portfolioSessionToken,
        excludedDocumentIds,
      );
      saveSelectedNameAnalysis(pendingAnalysis, selectedName);
    } catch (error) {
      reportClientOperationFailure("policy_selection_cleanup", error);
      dispatch({ type: "return-to-name-selection" });
      setError(ROLLBACK_ERROR_MESSAGE);
    }
  };

  return {
    selectedUploadFiles,
    isCheckingPasswords,
    isAnalyzing,
    isCompleting,
    isPreparingServer: workflow.phase === "preparing-server",
    analysisProgress: workflow.analysisProgress,
    pendingAnalysis:
      workflow.phase === "name-selection" ? workflow.pendingAnalysis : null,
    selectedName:
      workflow.phase === "name-selection" ? workflow.selectedName : "",
    setSelectedName: (selectedName: string) =>
      dispatch({ type: "select-name", selectedName }),
    error,
    inputRef,
    selectFiles,
    removeSelectedFile,
    updateSelectedFilePassword,
    handleSubmit,
    handleNameSelectionSubmit,
  };
}
