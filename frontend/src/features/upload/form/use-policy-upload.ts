import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useReducer, useRef } from "react";
import {
  type AnalyzedInsurance,
  type InsuranceAnalysis,
  getInsuredPersonName,
} from "../../analysis/types";
import { useInsuranceData } from "../../analysis/session/store";
import {
  deletePortfolioSessionDocuments,
  type PortfolioSessionResult,
} from "../../analysis/session/api";
import { PORTFOLIO_MAX_DOCUMENTS } from "@/shared/api/generated-runtime";
import { reportClientOperationFailure } from "@/shared/api/errors";
import type { UploadPolicyDocument } from "../types";
import { useCompletionDelay } from "./use-completion-delay";
import { usePolicyFiles } from "./use-policy-files";
import {
  DOCUMENT_CLEANUP_ERROR_MESSAGE,
  isAbortError,
  messageForFailedUploads,
  messageForSubmitFailure,
} from "../errors";
import { useServerDocumentCleanup } from "./use-document-cleanup";
import {
  initialPolicyUploadState,
  isUploadInFlight,
  policyUploadReducer,
} from "./upload-state";
import {
  submitPolicyUpload,
  type SubmitPolicyUploadProgressEvent,
  type SubmitPolicyUploadResult,
} from "../submission/submit";

type PolicyUploadOptions = {
  uploadPolicyDocument: UploadPolicyDocument;
  onAnalysisComplete?: (analysis: InsuranceAnalysis) => void;
  requiredInsuredPersonName?: string;
  existingDocuments: AnalyzedInsurance[];
  prepareServer: (signal?: AbortSignal) => Promise<void>;
  createSession: (signal?: AbortSignal) => Promise<PortfolioSessionResult>;
  deleteSessionDocuments?: (
    portfolioSessionToken: string,
    documentIds: string[],
    signal?: AbortSignal,
  ) => Promise<void>;
};

export function usePolicyUpload({
  uploadPolicyDocument,
  onAnalysisComplete,
  requiredInsuredPersonName,
  existingDocuments,
  prepareServer,
  createSession,
  deleteSessionDocuments = deletePortfolioSessionDocuments,
}: PolicyUploadOptions) {
  const {
    analysis: currentAnalysis,
    setAnalysis,
    expireSession,
  } = useInsuranceData();
  const router = useRouter();
  const activeUploadController = useRef<AbortController | null>(null);
  const activeSelectionController = useRef<AbortController | null>(null);
  const isMountedRef = useRef(false);
  const [uploadState, dispatch] = useReducer(
    policyUploadReducer,
    initialPolicyUploadState,
  );
  const { runAfterDelay } = useCompletionDelay();
  const { resolvePendingCleanup, rollbackSessionDocuments } =
    useServerDocumentCleanup(deleteSessionDocuments);
  const processingPhase = isUploadInFlight(uploadState)
    ? uploadState.phase
    : null;

  useEffect(() => {
    if (onAnalysisComplete) return;
    // This route is reached after a long-running upload, not through a Link.
    router.prefetch("/analysis");
  }, [onAnalysisComplete, router]);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      activeUploadController.current?.abort();
      activeSelectionController.current?.abort();
    };
  }, []);

  const completeAnalysis =
    onAnalysisComplete ??
    ((analysis: InsuranceAnalysis) => {
      setAnalysis(analysis);
      router.push("/analysis");
    });
  const {
    selectedFiles,
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
    markFileSucceeded,
    markFileRejected,
    resetProcessedFilesToIdle,
  } = usePolicyFiles({
    isLocked:
      uploadState.phase === "name-selection" || Boolean(processingPhase),
    maxSelectableFiles: Math.max(
      0,
      PORTFOLIO_MAX_DOCUMENTS - existingDocuments.length,
    ),
    onSelectionReset: () => dispatch({ type: "reset" }),
  });

  const completeWithSelectedPerson = (
    analysis: InsuranceAnalysis,
    personName: string,
  ) => {
    if (!isMountedRef.current) return;
    const filteredAnalysis = {
      ...analysis,
      selectedName: personName,
      insuranceDocuments: analysis.insuranceDocuments.filter(
        (insuranceDocument) =>
          getInsuredPersonName(insuranceDocument) === personName,
      ),
    };
    runAfterDelay(() => {
      completeAnalysis(filteredAnalysis);
    });
  };

  const handleUploadProgress = (event: SubmitPolicyUploadProgressEvent) => {
    if (!isMountedRef.current) return;
    switch (event.type) {
      case "upload-started":
        markSelectedFilesReading();
        return;
      case "server-ready":
        dispatch({ type: "server-ready" });
        return;
      case "file-succeeded":
        dispatch({ type: "uploaded" });
        markFileSucceeded(event.selectedFileId);
        return;
      case "file-rejected":
        dispatch({ type: "uploaded" });
        markFileRejected(event.selectedFileId, event.uploadError);
    }
  };

  const handleSubmitResult = (result: SubmitPolicyUploadResult) => {
    switch (result.kind) {
      case "cleanup-failed":
        setError(DOCUMENT_CLEANUP_ERROR_MESSAGE);
        return false;
      case "fingerprint-failed":
        reportClientOperationFailure("policy_fingerprint", result.error);
        setError(
          "PDF 파일을 확인하지 못했어요. 파일을 다시 선택한 뒤 시도해주세요.",
        );
        return false;
      case "file-errors":
        resetProcessedFilesToIdle();
        setError(messageForFailedUploads(result.uploadErrors));
        return false;
      case "cancelled":
        return false;
      case "duplicate-files":
        rejectDuplicateFiles(result.files);
        return false;
      case "missing-insured-person":
        failSelectedFiles(
          result.files,
          "MISSING_INSURED_PERSON",
          "피보험자를 확인할 수 없는 증권이에요.",
        );
        return false;
      case "insured-person-mismatch":
        resetProcessedFilesToIdle();
        setError(
          `${result.expectedName}님의 보험증권만 추가할 수 있어요. 같은 피보험자의 증권만 선택해주세요.`,
        );
        return false;
      case "failed":
        if (result.sessionExpired) expireSession();
        reportClientOperationFailure("policy_upload", result.error);
        resetProcessedFilesToIdle();
        setError(messageForSubmitFailure(result.error));
        return false;
      case "complete":
        dispatch({ type: "begin-completion" });
        completeWithSelectedPerson(result.analysis, result.selectedName);
        return true;
      case "select-name":
        dispatch({
          type: "require-name-selection",
          analysis: result.analysis,
          selectedName: result.selectedName,
        });
        return true;
    }
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (
      selectedFiles.length === 0 ||
      processingPhase ||
      uploadState.phase === "name-selection" ||
      isCheckingPasswords
    )
      return;

    dispatch({ type: "start", total: selectedFiles.length });
    activeUploadController.current?.abort();
    const uploadController = new AbortController();
    activeUploadController.current = uploadController;
    let retainUploadState = false;
    try {
      setError(null);
      const result = await submitPolicyUpload({
        input: {
          selectedFiles,
          currentAnalysis,
          existingDocuments,
          requiredInsuredPersonName,
          signal: uploadController.signal,
        },
        services: {
          prepareServer,
          createSession,
          uploadPolicyDocument,
          resolvePendingCleanup,
          rollbackSessionDocuments,
        },
        onProgress: handleUploadProgress,
      });

      if (!isMountedRef.current || uploadController.signal.aborted) return;
      retainUploadState = handleSubmitResult(result);
    } catch (error) {
      if (
        !isMountedRef.current ||
        uploadController.signal.aborted ||
        isAbortError(error)
      )
        return;
      reportClientOperationFailure("policy_upload", error);
      resetProcessedFilesToIdle();
      setError(messageForSubmitFailure(error));
    } finally {
      if (activeUploadController.current === uploadController) {
        activeUploadController.current = null;
      }
      if (isMountedRef.current && !retainUploadState) {
        dispatch({ type: "finish" });
      }
    }
  };

  const handleNameSelectionSubmit = async () => {
    if (uploadState.phase !== "name-selection" || !uploadState.selectedName)
      return;

    const { pendingAnalysis, selectedName } = uploadState;
    const excludedDocumentIds = pendingAnalysis.insuranceDocuments
      .filter((document) => getInsuredPersonName(document) !== selectedName)
      .map((document) => document.id);
    dispatch({ type: "begin-completion" });
    setError(null);
    activeSelectionController.current?.abort();
    const selectionController = new AbortController();
    activeSelectionController.current = selectionController;
    try {
      await deleteSessionDocuments(
        pendingAnalysis.portfolioSessionToken,
        excludedDocumentIds,
        selectionController.signal,
      );
      if (!isMountedRef.current || selectionController.signal.aborted) return;
      completeWithSelectedPerson(pendingAnalysis, selectedName);
    } catch (error) {
      if (
        !isMountedRef.current ||
        selectionController.signal.aborted ||
        isAbortError(error)
      )
        return;
      reportClientOperationFailure("policy_selection_cleanup", error);
      dispatch({ type: "return-to-name-selection" });
      setError(DOCUMENT_CLEANUP_ERROR_MESSAGE);
    } finally {
      if (activeSelectionController.current === selectionController) {
        activeSelectionController.current = null;
      }
    }
  };

  return {
    selectedFiles,
    isCheckingPasswords,
    processingPhase,
    analysisProgress: uploadState.analysisProgress,
    pendingAnalysis:
      uploadState.phase === "name-selection"
        ? uploadState.pendingAnalysis
        : null,
    selectedName:
      uploadState.phase === "name-selection" ? uploadState.selectedName : "",
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
