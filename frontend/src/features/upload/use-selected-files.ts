"use client";

import { useRef, useState } from "react";
import {
  PDF_MAX_BYTES,
  PORTFOLIO_MAX_DOCUMENTS,
} from "@/shared/api/generated-runtime";
import { isPdfPasswordProtected } from "./pdf-password-check";
import type { SelectedUploadFile } from "./types";
import {
  type ApiErrorCodeOrLocalUiCode,
  createFileFingerprint,
  toFiles,
} from "./upload-helpers";

// Owns the list of picked files and their per-file status/error/password
// state — selection, removal, password entry, and the fail/duplicate badges
// shown before and during upload. The submit transaction that actually
// uploads these files lives in use-orchestration.ts.
export function useSelectedFiles({
  isLocked,
  maxSelectableFiles,
  onSelectionReset,
}: {
  isLocked: boolean;
  maxSelectableFiles: number;
  onSelectionReset: () => void;
}) {
  const [selectedUploadFiles, setSelectedUploadFiles] = useState<
    SelectedUploadFile[]
  >([]);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const isCheckingPasswords = selectedUploadFiles.some(
    (selectedFile) => selectedFile.status === "checking",
  );

  const selectFiles = (files: FileList | File[]) => {
    if (isLocked) return;
    const incomingFiles = toFiles(files);
    onSelectionReset();
    if (incomingFiles.length === 0) {
      setSelectedUploadFiles([]);
      setError("올릴 파일을 찾지 못했어요. PDF를 다시 선택해주세요.");
      return;
    }
    if (incomingFiles.length > maxSelectableFiles) {
      setSelectedUploadFiles([]);
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
      setSelectedUploadFiles([]);
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
    setSelectedUploadFiles(selectedFiles);
    setError(null);
    flagPasswordProtectedFiles(selectedFiles);
  };

  // Fire-and-forget: check each newly selected file for an encryption
  // password so the field shows up before submit instead of after a failed
  // upload round trip. Matches by id so a removed/superseded file is a no-op.
  // A file left in "checking" keeps submit disabled forever, so both outcomes
  // of the check must clear it.
  const flagPasswordProtectedFiles = (files: SelectedUploadFile[]) => {
    const clearChecking = (fileId: string, needsPassword: boolean) => {
      setSelectedUploadFiles((current) =>
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
    setSelectedUploadFiles((current) => {
      const next = current.filter((selectedFile) => selectedFile.id !== fileId);
      if (next.length === 0 && inputRef.current) inputRef.current.value = "";
      return next;
    });
    onSelectionReset();
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

  const markSelectedFilesReading = () => {
    setSelectedUploadFiles((current) =>
      current.map((selectedFile) => ({
        ...selectedFile,
        status: "reading",
        errorCode: undefined,
        errorMessage: undefined,
      })),
    );
  };

  // Clear the transient "reading" state so files left untouched by an aborted
  // batch don't stay stuck mid-read.
  const resetReadingFilesToIdle = () => {
    setSelectedUploadFiles((current) =>
      current.map((selectedFile) =>
        selectedFile.status === "reading"
          ? { ...selectedFile, status: "idle" }
          : selectedFile,
      ),
    );
  };

  // Only accepted PDFs reach this stage, so the server's size gate has already
  // bounded the sequential reads used for local duplicate UX.
  const fingerprintSelectedFiles = async (files: SelectedUploadFile[]) => {
    const fingerprints: string[] = [];
    for (const selectedFile of files) {
      fingerprints.push(await createFileFingerprint(selectedFile.file));
    }
    return fingerprints;
  };

  return {
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
  };
}
