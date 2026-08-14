import { useRef, useState } from "react";
import {
  PDF_MAX_BYTES,
  PORTFOLIO_MAX_DOCUMENTS,
} from "@/shared/api/generated-runtime";
import { isPdfPasswordProtected } from "./pdf-password-check";
import type { PolicyUploadError } from "../api";
import type { SelectedPolicyFile } from "../types";
import type { SelectedFileErrorCode } from "../errors";

export function usePolicyFiles({
  isLocked,
  maxSelectableFiles,
  onSelectionReset,
}: {
  isLocked: boolean;
  maxSelectableFiles: number;
  onSelectionReset: () => void;
}) {
  const [selectedFiles, setSelectedFiles] = useState<SelectedPolicyFile[]>([]);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const isCheckingPasswords = selectedFiles.some(
    (selectedFile) => selectedFile.status === "checking",
  );

  const selectFiles = (files: FileList | File[]) => {
    if (isLocked) return;
    const incomingFiles = Array.from(files);
    onSelectionReset();
    if (incomingFiles.length === 0) {
      setSelectedFiles([]);
      setError("올릴 파일을 찾지 못했어요. PDF를 다시 선택해주세요.");
      return;
    }
    if (incomingFiles.length > maxSelectableFiles) {
      setSelectedFiles([]);
      setError(
        maxSelectableFiles > 0
          ? `보험증권은 최대 ${PORTFOLIO_MAX_DOCUMENTS}개까지 분석할 수 있어요. 지금은 ${maxSelectableFiles}개까지 추가할 수 있어요.`
          : `보험증권은 최대 ${PORTFOLIO_MAX_DOCUMENTS}개까지 분석할 수 있어요.`,
      );
      return;
    }
    const oversizedFiles = incomingFiles.filter(
      (file) => file.size > PDF_MAX_BYTES,
    );
    if (oversizedFiles.length > 0) {
      setSelectedFiles([]);
      setError(
        `파일이 너무 커요. PDF 한 개당 최대 ${PDF_MAX_BYTES / (1024 * 1024)}MB까지 올릴 수 있어요.`,
      );
      return;
    }

    const selectedFiles = incomingFiles.map((file, index) => ({
      id: `${Date.now()}-${index}-${file.name}-${file.size}`,
      file,
      status: "checking" as const,
    }));
    setSelectedFiles(selectedFiles);
    setError(null);
    flagPasswordProtectedFiles(selectedFiles);
  };

  // Fire-and-forget: check each newly selected file for an encryption
  // password so the field shows up before submit instead of after a failed
  // upload round trip. Matches by id so a removed/superseded file is a no-op.
  // A file left in "checking" keeps submit disabled forever, so both outcomes
  // of the check must clear it.
  const flagPasswordProtectedFiles = (files: SelectedPolicyFile[]) => {
    const clearChecking = (fileId: string, needsPassword: boolean) => {
      setSelectedFiles((current) =>
        current.map((currentFile) => {
          if (currentFile.id !== fileId) return currentFile;
          if (currentFile.status !== "checking") return currentFile;
          if (needsPassword && !currentFile.errorCode) {
            return {
              ...currentFile,
              status: "idle" as const,
              errorCode: "PDF_PASSWORD_REQUIRED",
              errorMessage: "PDF 비밀번호를 입력해주세요.",
            };
          }
          return { ...currentFile, status: "idle" as const };
        }),
      );
    };

    for (const selectedFile of files) {
      void isPdfPasswordProtected(selectedFile.file)
        .then((needsPassword) => clearChecking(selectedFile.id, needsPassword))
        .catch(() => clearChecking(selectedFile.id, false));
    }
  };

  const removeSelectedFile = (fileId: string) => {
    setSelectedFiles((current) => {
      const next = current.filter((selectedFile) => selectedFile.id !== fileId);
      if (next.length === 0 && inputRef.current) inputRef.current.value = "";
      return next;
    });
    onSelectionReset();
    setError(null);
  };

  const updateSelectedFilePassword = (fileId: string, password: string) => {
    setSelectedFiles((current) =>
      current.map((selectedFile) =>
        selectedFile.id === fileId
          ? { ...selectedFile, password }
          : selectedFile,
      ),
    );
  };

  const failSelectedFiles = (
    files: Array<{ id: string; fileName: string }>,
    code: SelectedFileErrorCode,
    message: string,
  ) => {
    const failedIds = new Set(files.map((file) => file.id));
    setSelectedFiles((current) =>
      current.map((selectedFile) => {
        if (failedIds.has(selectedFile.id)) {
          return {
            ...selectedFile,
            status: "failed",
            errorCode: code,
            errorMessage: message,
          };
        }
        if (
          selectedFile.status === "reading" ||
          selectedFile.status === "done"
        ) {
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

  const markSelectedFilesReading = () => {
    setSelectedFiles((current) =>
      current.map((selectedFile) => ({
        ...selectedFile,
        status: "reading",
        errorCode: undefined,
        errorMessage: undefined,
      })),
    );
  };

  const markFileSucceeded = (fileId: string) => {
    setSelectedFiles((current) =>
      current.map((file) =>
        file.id === fileId ? { ...file, status: "done" } : file,
      ),
    );
  };

  const markFileRejected = (
    fileId: string,
    uploadError?: PolicyUploadError,
  ) => {
    setSelectedFiles((current) =>
      current.map((file) => {
        if (file.id !== fileId) return file;
        return uploadError
          ? {
              ...file,
              status: "failed",
              errorCode: uploadError.code,
              errorMessage: uploadError.userMessage,
            }
          : { ...file, status: "idle" };
      }),
    );
  };

  const resetProcessedFilesToIdle = () => {
    setSelectedFiles((current) =>
      current.map((selectedFile) =>
        selectedFile.status === "reading" || selectedFile.status === "done"
          ? { ...selectedFile, status: "idle" }
          : selectedFile,
      ),
    );
  };

  return {
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
  };
}
