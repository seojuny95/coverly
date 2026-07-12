"use client";

import { type DragEvent, useState } from "react";
import type {
  AnalyzedInsurance,
  InsuranceAnalysis,
} from "../insurance-analysis/insurance-analysis-store";
import { uploadInsurance as uploadInsuranceRequest } from "./upload-insurance";
import {
  primaryButtonClassName,
  secondaryButtonClassName,
} from "../../components/coverly-brand";
import { AnalysisProgress } from "./analysis-progress";
import { SelectedFileList } from "./selected-file-list";
import type { UploadInsurance } from "./upload-types";
import {
  getInsuranceNameOptions,
  useUploadOrchestration,
} from "./use-upload-orchestration";

export type { UploadInsurance };

type InsuranceUploadFormProps = {
  uploadInsurance?: UploadInsurance;
  onAnalysisComplete?: (analysis: InsuranceAnalysis) => void;
  navigateToAnalysis?: () => void;
  fixedSelectedName?: string;
  existingDocuments?: AnalyzedInsurance[];
  surface?: "page" | "modal";
};

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
  const {
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
    handleSubmit,
    handleNameSelectionSubmit,
  } = useUploadOrchestration({
    uploadInsurance,
    onAnalysisComplete,
    navigateToAnalysis,
    fixedSelectedName,
    existingDocuments,
  });

  // Drag-hover styling is purely presentational, so it stays local; the drop
  // handler just forwards the files to the orchestration hook.
  const [isDragging, setIsDragging] = useState(false);
  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDragging(false);
    selectFiles(event.dataTransfer.files);
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
