"use client";

import { useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
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
import { type DragEvent, type FormEvent, useRef, useState } from "react";

import {
  type InsuranceUploadResult,
  UploadInsuranceError,
  uploadInsurance as uploadInsuranceRequest,
} from "./upload-insurance";
import {
  primaryButtonClassName,
  secondaryButtonClassName,
} from "../../components/coverly-brand";
import { fileHasPdfMagic } from "./pdf-magic";
import { AnalysisProgress } from "./analysis-progress";
import { SelectedFileList } from "./selected-file-list";
import type { SelectedUploadFile } from "./upload-types";

export type UploadInsurance = (file: File) => Promise<InsuranceUploadResult>;

type InsuranceUploadFormProps = {
  uploadInsurance?: UploadInsurance;
  onAnalysisComplete?: (analysis: InsuranceAnalysis) => void;
  navigateToAnalysis?: () => void;
  fixedSelectedName?: string;
  existingDocuments?: AnalyzedInsurance[];
  surface?: "page" | "modal";
};

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

export function InsuranceUploadForm({
  uploadInsurance = uploadInsuranceRequest,
  onAnalysisComplete,
  // Intentionally a no-op default: navigation now happens inside the default
  // onAnalysisComplete (via router.push), not through this callback. Callers
  // that pass it use it for side effects like closing the upload modal.
  navigateToAnalysis = () => {},
  fixedSelectedName,
  existingDocuments = [],
  surface = "page",
}: InsuranceUploadFormProps) {
  const { setAnalysis } = useInsuranceData();
  const router = useRouter();
  const uploadMutation = useMutation({ mutationFn: uploadInsurance });
  const completeAnalysis =
    onAnalysisComplete ??
    ((analysis: InsuranceAnalysis) => {
      setAnalysis(analysis);
      router.push("/analysis");
    });
  const [selectedUploadFiles, setSelectedUploadFiles] = useState<
    SelectedUploadFile[]
  >([]);
  const [isDragging, setIsDragging] = useState(false);
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

    setSelectedUploadFiles(
      incomingFiles.map((file, index) => ({
        id: `${Date.now()}-${index}-${file.name}-${file.size}`,
        file,
        status: "idle",
      })),
    );
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

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDragging(false);
    selectFiles(event.dataTransfer.files);
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
            const result = await uploadMutation.mutateAsync(selectedFile.file);
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
              message: uploadError.userMessage,
            };
          }
        }),
      );

      const failedUploads = uploadResults.filter(
        (result) => result.status === "rejected",
      );
      if (failedUploads.length > 0) {
        setError(
          "텍스트를 추출할 수 없는 PDF가 있어요. 표시된 파일을 제거한 뒤 다시 시도해주세요.",
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
      setError(
        "피보험자를 확인할 수 없는 증권이 있어요. 피보험자가 확인된 증권만 분석할 수 있어요.",
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

  const selectedFiles = selectedUploadFiles.map(
    (selectedFile) => selectedFile.file,
  );
  const selectedBytes = selectedFiles.reduce((sum, file) => sum + file.size, 0);
  const fileSizeLabel =
    selectedFiles.length > 0
      ? `${selectedFiles.length}개 · ${(selectedBytes / 1024 / 1024).toFixed(2)} MB`
      : "파일당 최대 10MB";
  const isModal = surface === "modal";
  const submitLabel = isModal ? "분석에 추가하기" : "내 보험 분석하기";
  const dropzoneTitle = fixedSelectedName
    ? `${fixedSelectedName}(피보험자)의 보험증권 PDF만 올릴 수 있어요`
    : "보험증권 PDF를 올려주세요";
  const dropzoneDescription = isModal ? "" : `PDF · ${fileSizeLabel}`;

  if (isAnalyzing) {
    return (
      <AnalysisProgress
        progress={analysisProgress}
        files={selectedUploadFiles.map((selectedFile) => ({
          name: selectedFile.file.name,
          status:
            selectedFile.status === "done" ? "done" : ("reading" as const),
        }))}
        surface={surface}
      />
    );
  }

  return (
    <form
      className={isModal ? "w-full max-w-none" : "w-full max-w-2xl"}
      onSubmit={handleSubmit}
    >
      <section>
        <div>
          <div
            data-testid="insurance-upload-dropzone"
            onDragEnter={(event) => {
              event.preventDefault();
              setIsDragging(true);
            }}
            onDragOver={(event) => {
              event.preventDefault();
              setIsDragging(true);
            }}
            onDragLeave={(event) => {
              event.preventDefault();
              setIsDragging(false);
            }}
            onDrop={handleDrop}
            className={`upload-dropzone relative flex flex-col items-center justify-center overflow-hidden rounded-2xl border border-dashed px-5 text-center transition-colors ${
              isDragging
                ? "border-blue-600 bg-blue-50"
                : isModal
                  ? "border-zinc-200 bg-zinc-50"
                  : "border-zinc-200 bg-white"
            } ${isModal ? "min-h-44 py-8" : "min-h-64 py-12"}`}
          >
            <span className="relative mb-5 grid size-11 place-items-center rounded-xl border border-zinc-200 bg-white shadow-[5px_5px_0_#e8edff]">
              <span className="grid grid-cols-2 gap-1" aria-hidden="true">
                <span className="size-1.5 bg-zinc-300" />
                <span className="size-1.5 bg-blue-600" />
                <span className="size-1.5 bg-zinc-300" />
                <span className="size-1.5 bg-zinc-300" />
              </span>
            </span>
            <p
              className={`relative font-medium text-zinc-950 ${
                isModal ? "text-base" : "text-base"
              }`}
            >
              {dropzoneTitle}
            </p>
            {dropzoneDescription ? (
              <p className="relative mt-2 text-sm leading-6 text-zinc-500">
                {dropzoneDescription}
              </p>
            ) : null}
            <p
              className={`relative mt-1 text-xs text-zinc-400 ${
                isModal ? "" : "hidden"
              }`}
            >
              {fileSizeLabel}
            </p>

            <input
              ref={inputRef}
              id="insurance-file"
              className="sr-only"
              type="file"
              accept="application/pdf,.pdf"
              multiple
              aria-label="PDF 파일 선택"
              onChange={(event) => {
                if (event.target.files) selectFiles(event.target.files);
              }}
            />
            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              className={`relative mt-6 ${secondaryButtonClassName}`}
            >
              PDF 불러오기
            </button>
          </div>

          {isModal ? null : (
            <div className="mt-3 flex flex-wrap items-center justify-center gap-x-5 gap-y-1 text-xs text-zinc-400">
              <span className="flex items-center gap-1.5">
                <ReassuranceCheckIcon />
                개인정보는 가려서 처리해요
              </span>
              <span className="flex items-center gap-1.5">
                <ReassuranceCheckIcon />
                가입 권유 전화가 가지 않아요
              </span>
            </div>
          )}

          <div className="mt-4 flex flex-col gap-4">
            <SelectedFileList
              files={selectedUploadFiles}
              surface={surface}
              onRemove={removeSelectedFile}
              disableRemove={isAnalyzing}
            />
            <button
              type="submit"
              disabled={selectedUploadFiles.length === 0 || isAnalyzing}
              className={`${primaryButtonClassName} self-stretch ${isModal ? "" : "sm:self-end"}`}
            >
              {isAnalyzing ? "보험 정리 중이에요" : submitLabel}
            </button>
          </div>

          {pendingAnalysis ? (
            <NameSelectionPanel
              options={getInsuranceNameOptions(
                pendingAnalysis.insuranceDocuments,
              )}
              selectedName={selectedName}
              onSelectedNameChange={setSelectedName}
              onContinue={handleNameSelectionSubmit}
            />
          ) : null}

          {error ? (
            <p
              role="alert"
              className="mt-4 rounded-xl border border-zinc-200 bg-white px-4 py-3 text-sm leading-6 text-zinc-700 shadow-[5px_5px_0_#f4f4f5]"
            >
              {error}
            </p>
          ) : null}
        </div>
      </section>
    </form>
  );
}

function ReassuranceCheckIcon() {
  return (
    <svg
      aria-hidden="true"
      className="size-3 text-blue-600"
      viewBox="0 0 14 14"
      fill="none"
    >
      <path
        d="m3 7 2.5 2.5L11 4.5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="square"
      />
    </svg>
  );
}

function isFileSpecificUploadError(err: unknown) {
  if (!(err instanceof UploadInsuranceError)) return false;
  if (err.code === "UPLOAD_NETWORK_ERROR") return false;
  if (err.status && err.status >= 500) return false;
  return true;
}

async function createFileFingerprint(file: File) {
  const buffer = await file.arrayBuffer();
  const digest = await crypto.subtle.digest("SHA-256", buffer);
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

function getInsuranceNameOptions(insuranceDocuments: AnalyzedInsurance[]) {
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

function NameSelectionPanel({
  options,
  selectedName,
  onSelectedNameChange,
  onContinue,
}: {
  options: Array<{ name: string; count: number }>;
  selectedName: string;
  onSelectedNameChange: (name: string) => void;
  onContinue: () => void;
}) {
  return (
    <div className="mt-4 rounded-xl border border-zinc-200 bg-white px-4 py-4 shadow-[5px_5px_0_#f4f4f5]">
      <p className="text-sm font-semibold text-zinc-950">
        피보험자가 여러 명 있어요
      </p>
      <p className="mt-1 text-sm leading-6 text-zinc-500">
        결과로 볼 피보험자를 선택하세요. 선택한 피보험자의 증권만 보여드려요.
      </p>

      <div className="mt-4 grid gap-2">
        {options.map((option, index) => {
          const inputId = `insurance-person-name-${index}`;
          return (
            <label
              key={option.name}
              htmlFor={inputId}
              className={`flex cursor-pointer items-center justify-between rounded-lg border px-3 py-3 text-sm transition-colors ${
                selectedName === option.name
                  ? "border-blue-600 bg-blue-50"
                  : "border-zinc-200 bg-white hover:bg-zinc-50"
              }`}
            >
              <span className="flex items-center gap-3">
                <input
                  id={inputId}
                  type="radio"
                  name="insurance-person-name"
                  value={option.name}
                  checked={selectedName === option.name}
                  onChange={(event) => onSelectedNameChange(event.target.value)}
                  className="h-4 w-4 accent-[#2563EB]"
                />
                <span className="font-medium text-zinc-800">{option.name}</span>
              </span>
              <span className="text-zinc-500">{option.count}개</span>
            </label>
          );
        })}
      </div>

      <button
        type="button"
        onClick={onContinue}
        disabled={!selectedName}
        className={`mt-4 ${primaryButtonClassName}`}
      >
        선택한 피보험자로 보기
      </button>
    </div>
  );
}
