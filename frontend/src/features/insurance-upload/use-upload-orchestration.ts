"use client";

import { useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useRef, useState } from "react";
import {
  type AnalyzedInsurance,
  type InsuranceAnalysis,
  getInsuredPersonName,
  useInsuranceData,
} from "../insurance-analysis/insurance-analysis-store";
import {
  findByteIdenticalDuplicateIndexes,
  findDuplicatePolicyDocuments,
} from "../insurance-analysis/policy-identity";
import { UploadInsuranceError } from "./upload-insurance";
import { fileHasPdfMagic, fileLooksEncryptedPdf } from "./pdf-magic";
import type { SelectedUploadFile, UploadInsurance } from "./upload-types";

const MAX_PDF_BYTES = 10 * 1024 * 1024;

function validateFile(file: File): string | null {
  const isPdf =
    file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
  if (!isPdf) return "PDF 파일만 올릴 수 있어요.";
  if (file.size > MAX_PDF_BYTES) {
    return "파일이 너무 커요. 최대 10MB까지 올릴 수 있어요.";
  }
  return null;
}

function toFiles(files: FileList | File[]): File[] {
  return Array.from(files);
}

function isFileSpecificUploadError(err: unknown) {
  if (!(err instanceof UploadInsuranceError)) return false;
  if (err.code === "UPLOAD_NETWORK_ERROR") return false;
  if (err.status && err.status >= 500) return false;
  return true;
}

function isPasswordUploadError(code: string) {
  return code === "PDF_PASSWORD_REQUIRED" || code === "PDF_PASSWORD_INCORRECT";
}

function isPreflightPasswordError(code?: string) {
  return code === "PDF_PASSWORD_REQUIRED";
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

// Owns the whole upload lifecycle: file selection/validation, byte-dedup, PDF
// content check, parallel upload with per-file progress, post-parse duplicate
// + insured-name resolution, and error/degrade handling. The form component
// consumes the returned state and handlers and renders; all the async flow and
// state transitions live here.
export function useUploadOrchestration({
  uploadInsurance,
  onAnalysisComplete,
  navigateToAnalysis,
  fixedSelectedName,
  existingDocuments,
}: {
  uploadInsurance: UploadInsurance;
  onAnalysisComplete?: (analysis: InsuranceAnalysis) => void;
  navigateToAnalysis: () => void;
  fixedSelectedName?: string;
  existingDocuments: AnalyzedInsurance[];
}) {
  const { setAnalysis } = useInsuranceData();
  const router = useRouter();
  const uploadMutation = useMutation({ mutationFn: uploadInsurance });

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

  const selectFiles = (files: FileList | File[]) => {
    const incomingFiles = toFiles(files);
    if (incomingFiles.length === 0) {
      setSelectedUploadFiles([]);
      setPendingAnalysis(null);
      setSelectedName("");
      setError("올릴 파일을 찾지 못했어요. PDF를 다시 선택해주세요.");
      return;
    }

    const invalidFile = incomingFiles.find((file) => validateFile(file));
    if (invalidFile) {
      const validationError = validateFile(invalidFile);
      setSelectedUploadFiles([]);
      setPendingAnalysis(null);
      setSelectedName("");
      setError(validationError);
      if (inputRef.current) inputRef.current.value = "";
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

    void Promise.all(
      selectedFiles.map(async (selectedFile) => ({
        id: selectedFile.id,
        isEncrypted: await fileLooksEncryptedPdf(selectedFile.file),
      })),
    ).then((inspectedFiles) => {
      const encryptedIds = new Set(
        inspectedFiles
          .filter((inspectedFile) => inspectedFile.isEncrypted)
          .map((inspectedFile) => inspectedFile.id),
      );
      if (encryptedIds.size === 0) {
        return;
      }

      setSelectedUploadFiles((current) =>
        current.map((selectedFile) => {
          if (!encryptedIds.has(selectedFile.id)) {
            return selectedFile;
          }

          if (isPreflightPasswordError(selectedFile.errorCode)) {
            return selectedFile;
          }

          return {
            ...selectedFile,
            errorCode: "PDF_PASSWORD_REQUIRED",
            errorMessage: "잠긴 PDF예요. 비밀번호를 먼저 입력해주세요.",
          };
        }),
      );
    });
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
    code: string,
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

  // Used by both duplicate paths: the byte-identical pre-upload check and the
  // post-parse semantic check.
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
    if (selectedUploadFiles.length === 0 || isAnalyzing) return;

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
    try {
      const fileFingerprints = await Promise.all(
        selectedUploadFiles.map((selectedFile) =>
          createFileFingerprint(selectedFile.file),
        ),
      );

      // Reject files whose bytes are not actually a PDF (e.g. an image renamed
      // to .pdf). The backend re-validates content and remains the authoritative
      // gate; this is fast client-side feedback.
      const contentIsPdf = await Promise.all(
        selectedUploadFiles.map((selectedFile) =>
          fileHasPdfMagic(selectedFile.file),
        ),
      );
      const invalidTypeFiles = selectedUploadFiles.filter(
        (_, index) => !contentIsPdf[index],
      );
      if (invalidTypeFiles.length > 0) {
        failSelectedFiles(
          invalidTypeFiles.map((selectedFile) => ({
            id: selectedFile.id,
            fileName: selectedFile.file.name,
          })),
          "INVALID_PDF",
          "PDF 형식이 아니에요.",
        );
        return;
      }

      // Catch byte-identical re-uploads before spending a full parse + LLM pass.
      const byteIdenticalIndexes = findByteIdenticalDuplicateIndexes({
        fingerprints: fileFingerprints,
        existingDocuments,
      });
      if (byteIdenticalIndexes.size > 0) {
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

      const uploadResults = await Promise.all(
        selectedUploadFiles.map(async (selectedFile, index) => {
          try {
            const uploadInput = selectedFile.password
              ? { file: selectedFile.file, password: selectedFile.password }
              : { file: selectedFile.file };
            const result = await uploadMutation.mutateAsync(uploadInput);
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
              document: {
                id: `${Date.now()}-${index}-${selectedFile.file.name}`,
                fileName: selectedFile.file.name,
                fileFingerprint: fileFingerprints[index],
                result,
              },
            };
          } catch (err) {
            if (!isFileSpecificUploadError(err)) throw err;

            const uploadError = err as UploadInsuranceError;
            setAnalysisProgress((current) => ({
              ...current,
              completed: current.completed + 1,
            }));
            setSelectedUploadFiles((current) =>
              current.map((currentFile) =>
                currentFile.id === selectedFile.id
                  ? {
                      ...currentFile,
                      status: "failed",
                      errorCode: uploadError.code,
                      errorMessage: uploadError.userMessage,
                    }
                  : currentFile,
              ),
            );
            return {
              status: "rejected" as const,
              fileName: selectedFile.file.name,
              code: uploadError.code,
              message: uploadError.userMessage,
            };
          }
        }),
      );

      const failedUploads = uploadResults.filter(
        (result) => result.status === "rejected",
      );
      if (failedUploads.length > 0) {
        const hasPasswordErrors = failedUploads.some(
          (result) =>
            result.status === "rejected" && isPasswordUploadError(result.code),
        );
        const onlyPasswordErrors = failedUploads.every(
          (result) =>
            result.status === "rejected" && isPasswordUploadError(result.code),
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

      const insuranceDocuments = uploadResults.flatMap((result) =>
        result.status === "fulfilled" ? [result.document] : [],
      );
      const selectedFileIdsByDocumentId = new Map(
        uploadResults.flatMap((result) =>
          result.status === "fulfilled"
            ? [[result.document.id, result.selectedFileId]]
            : [],
        ),
      );
      const analysis = {
        generatedAt: new Date().toISOString(),
        insuranceDocuments,
      };
      shouldKeepProgress = continueWithNameValidation(
        analysis,
        selectedFileIdsByDocumentId,
      );
    } catch (err) {
      setSelectedUploadFiles((current) =>
        current.map((selectedFile) =>
          selectedFile.status === "reading"
            ? { ...selectedFile, status: "idle" }
            : selectedFile,
        ),
      );
      if (err instanceof UploadInsuranceError) {
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

  const continueWithNameValidation = (
    analysis: InsuranceAnalysis,
    selectedFileIdsByDocumentId: Map<string, string>,
  ) => {
    const insuranceDocumentsWithoutName = analysis.insuranceDocuments.filter(
      (insuranceDocument) => !getInsuredPersonName(insuranceDocument),
    );
    if (insuranceDocumentsWithoutName.length > 0) {
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

  const handleNameSelectionSubmit = () => {
    if (!pendingAnalysis || !selectedName) return;
    saveSelectedNameAnalysis(pendingAnalysis, selectedName);
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
