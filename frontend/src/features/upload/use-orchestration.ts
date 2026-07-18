"use client";

import { useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useRef, useState } from "react";
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
import { UploadInsuranceError, type UploadErrorCode } from "./api";
import type { SelectedUploadFile, UploadInsurance } from "./types";

function toFiles(files: FileList | File[]): File[] {
  return Array.from(files);
}

function isFileSpecificUploadError(err: unknown) {
  if (!(err instanceof UploadInsuranceError)) return false;
  if (err.code === "UPLOAD_NETWORK_ERROR") return false;
  if (err.status && err.status >= 500) return false;
  return true;
}

function isPasswordUploadError(code: UploadErrorCode) {
  return code === "PDF_PASSWORD_REQUIRED" || code === "PDF_PASSWORD_INCORRECT";
}

const ROLLBACK_ERROR_MESSAGE =
  "업로드한 문서를 정리하지 못했어요. 다시 시도해주세요.";

class UploadRollbackError extends Error {
  constructor() {
    super(ROLLBACK_ERROR_MESSAGE);
    this.name = "UploadRollbackError";
  }
}

async function createFileFingerprint(file: File) {
  const buffer = await file.arrayBuffer();
  const digest = await crypto.subtle.digest("SHA-256", buffer);
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

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

// Owns the whole upload lifecycle: file selection, byte-dedup, parallel upload
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
  const { analysis: currentAnalysis, setAnalysis } = useInsuranceData();
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
  const [selectedUploadFiles, setSelectedUploadFiles] = useState<
    SelectedUploadFile[]
  >([]);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisProgress, setAnalysisProgress] = useState({
    completed: 0,
    total: 0,
  });
  const [pendingAnalysis, setPendingAnalysis] =
    useState<InsuranceAnalysis | null>(null);
  const [selectedName, setSelectedName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const pendingCleanupRef = useRef<{
    portfolioSessionToken: string;
    documentIds: string[];
  } | null>(null);

  const selectFiles = (files: FileList | File[]) => {
    if (pendingAnalysis || isAnalyzing) return;
    const incomingFiles = toFiles(files);
    if (incomingFiles.length === 0) {
      setSelectedUploadFiles([]);
      setPendingAnalysis(null);
      setSelectedName("");
      setError("올릴 파일을 찾지 못했어요. PDF를 다시 선택해주세요.");
      return;
    }

    const selectedFiles = incomingFiles.map((file, index) => ({
      id: `${Date.now()}-${index}-${file.name}-${file.size}`,
      file,
      status: "idle" as const,
    }));
    setSelectedUploadFiles(selectedFiles);
    setPendingAnalysis(null);
    setSelectedName("");
    setError(null);
  };

  const removeSelectedFile = (fileId: string) => {
    setSelectedUploadFiles((current) => {
      const next = current.filter((selectedFile) => selectedFile.id !== fileId);
      if (next.length === 0 && inputRef.current) inputRef.current.value = "";
      return next;
    });
    setPendingAnalysis(null);
    setSelectedName("");
    setError(null);
  };

  const updateSelectedFilePassword = (fileId: string, password: string) => {
    setSelectedUploadFiles((current) =>
      current.map((selectedFile) =>
        selectedFile.id === fileId
          ? { ...selectedFile, password }
          : selectedFile,
      ),
    );
  };

  // Mark the given selected files as failed with a shared code + message and
  // surface one "remove and retry" summary. Non-listed files are left as-is.
  const failSelectedFiles = (
    files: Array<{ id: string; fileName: string }>,
    code: ApiErrorCodeOrLocalUiCode,
    message: string,
  ) => {
    const failedIds = new Set(files.map((file) => file.id));
    setSelectedUploadFiles((current) =>
      current.map((selectedFile) => {
        if (failedIds.has(selectedFile.id)) {
          return {
            ...selectedFile,
            status: "failed",
            errorCode: code,
            errorMessage: message,
          };
        }
        // This aborts the batch, so clear the transient "reading" state set at
        // submit — untouched files must not stay stuck mid-read.
        if (selectedFile.status === "reading") {
          return { ...selectedFile, status: "idle" as const };
        }
        return selectedFile;
      }),
    );
    setError(
      `${message} ${files
        .map((file) => file.fileName)
        .join(", ")} 파일을 제거하고 다시 시도해주세요.`,
    );
  };

  const rejectDuplicateFiles = (
    duplicates: Array<{ id: string; fileName: string }>,
  ) => {
    failSelectedFiles(
      duplicates,
      "DUPLICATE_POLICY",
      "이미 올린 보험증권이에요.",
    );
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (selectedUploadFiles.length === 0 || isAnalyzing || pendingAnalysis)
      return;

    const pendingCleanup = pendingCleanupRef.current;
    if (pendingCleanup) {
      setIsAnalyzing(true);
      setError(null);
      try {
        await deleteSessionDocuments(
          currentAnalysis?.portfolioSessionToken ??
            pendingCleanup.portfolioSessionToken,
          pendingCleanup.documentIds,
        );
        pendingCleanupRef.current = null;
      } catch {
        setError(ROLLBACK_ERROR_MESSAGE);
        setIsAnalyzing(false);
        return;
      }
    }

    setIsAnalyzing(true);
    setAnalysisProgress({ completed: 0, total: selectedUploadFiles.length });
    setSelectedUploadFiles((current) =>
      current.map((selectedFile) => ({
        ...selectedFile,
        status: "reading",
        errorCode: undefined,
        errorMessage: undefined,
      })),
    );
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
    let successfulDocumentIds = [...assignedDocumentIds.values()];
    const rollbackSuccessfulDocuments = async () => {
      if (!portfolioSessionToken || successfulDocumentIds.length === 0) return;
      try {
        await deleteSessionDocuments(
          portfolioSessionToken,
          successfulDocumentIds,
        );
        pendingCleanupRef.current = null;
        successfulDocumentIds = [];
      } catch {
        pendingCleanupRef.current = {
          portfolioSessionToken,
          documentIds: [...successfulDocumentIds],
        };
        throw new UploadRollbackError();
      }
    };
    try {
      const portfolioSession = currentAnalysis
        ? {
            portfolioSessionToken: currentAnalysis.portfolioSessionToken,
            expiresAt: currentAnalysis.portfolioSessionExpiresAt,
          }
        : await sessionMutation.mutateAsync();
      portfolioSessionToken = portfolioSession.portfolioSessionToken;

      const uploadResults = await Promise.all(
        selectedUploadFiles.map(async (selectedFile) => {
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
        }),
      );

      const failedUploads = uploadResults.filter(
        (result) => result.status === "rejected",
      );
      if (failedUploads.length > 0) {
        await rollbackSuccessfulDocuments();
        const unexpectedFailure = failedUploads.find(
          (result) => !result.uploadError,
        );
        if (unexpectedFailure) throw unexpectedFailure.error;
        const uploadErrors = failedUploads.flatMap((result) =>
          result.uploadError ? [result.uploadError] : [],
        );
        const hasPasswordErrors = failedUploads.some(
          (result) =>
            result.uploadError &&
            isPasswordUploadError(result.uploadError.code),
        );
        const onlyPasswordErrors = uploadErrors.every((uploadError) =>
          isPasswordUploadError(uploadError.code),
        );
        setError(
          onlyPasswordErrors
            ? "비밀번호가 필요한 PDF가 있어요. 표시된 파일에 비밀번호를 입력한 뒤 다시 시도해주세요."
            : hasPasswordErrors
              ? "일부 PDF는 비밀번호가 필요해요. 읽을 수 없는 PDF는 제거한 뒤 다시 시도해주세요."
              : "텍스트를 추출할 수 없는 PDF가 있어요. 표시된 파일을 제거한 뒤 다시 시도해주세요.",
        );
        return;
      }

      // Only accepted PDFs reach this stage, so the server's size gate has
      // already bounded the sequential reads used for local duplicate UX.
      const fileFingerprints: string[] = [];
      for (const selectedFile of selectedUploadFiles) {
        fileFingerprints.push(await createFileFingerprint(selectedFile.file));
      }
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
        insuranceDocuments,
      };
      shouldKeepProgress = await continueWithNameValidation(
        analysis,
        selectedFileIdsByDocumentId,
        rollbackSuccessfulDocuments,
      );
    } catch (err) {
      if (
        !(err instanceof UploadRollbackError) &&
        successfulDocumentIds.length > 0
      ) {
        try {
          await rollbackSuccessfulDocuments();
        } catch {
          err = new UploadRollbackError();
        }
      }
      setSelectedUploadFiles((current) =>
        current.map((selectedFile) =>
          selectedFile.status === "reading"
            ? { ...selectedFile, status: "idle" }
            : selectedFile,
        ),
      );
      if (err instanceof UploadRollbackError) {
        setError(ROLLBACK_ERROR_MESSAGE);
      } else if (err instanceof UploadInsuranceError) {
        setError(err.userMessage);
      } else {
        setError(
          err instanceof Error
            ? err.message
            : "업로드에 실패했어요. 잠시 후 다시 시도해주세요.",
        );
      }
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
    completeAnalysis(filteredAnalysis);
    navigateToAnalysis();
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
      saveSelectedNameAnalysis(pendingAnalysis, selectedName);
    } catch {
      setError(ROLLBACK_ERROR_MESSAGE);
    } finally {
      setIsAnalyzing(false);
    }
  };

  return {
    selectedUploadFiles,
    isAnalyzing,
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

type ApiErrorCodeOrLocalUiCode = Exclude<
  UploadErrorCode,
  "UPLOAD_NETWORK_ERROR" | "UPLOAD_FAILED"
>;
