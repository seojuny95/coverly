"use client";

import { type DragEvent, type FormEvent, useRef, useState } from "react";

import {
  type PolicyUploadResult,
  UploadPolicyError,
  uploadPolicy as uploadPolicyRequest,
} from "./upload-policy";

export type UploadPolicy = (file: File) => Promise<PolicyUploadResult>;

type UploadFormProps = {
  uploadPolicy?: UploadPolicy;
};

const MAX_PDF_BYTES = 10 * 1024 * 1024;

function validateFile(file: File): string | null {
  const isPdf =
    file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
  if (!isPdf) return "PDF 파일만 업로드할 수 있습니다.";
  if (file.size > MAX_PDF_BYTES) return "파일이 너무 큽니다 (최대 10MB).";
  return null;
}

function toFiles(files: FileList | File[]): File[] {
  return Array.from(files);
}

export function UploadForm({
  uploadPolicy = uploadPolicyRequest,
}: UploadFormProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [result, setResult] = useState<PolicyUploadResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const selectFile = (file: File | undefined) => {
    if (!file) return;
    const validationError = validateFile(file);
    if (validationError) {
      setSelectedFile(null);
      setResult(null);
      setError(validationError);
      if (inputRef.current) inputRef.current.value = "";
      return;
    }
    setSelectedFile(file);
    setResult(null);
    setError(null);
  };

  const selectDroppedFiles = (files: FileList | File[]) => {
    const droppedFiles = toFiles(files);
    if (droppedFiles.length === 0) {
      setSelectedFile(null);
      setResult(null);
      setError("업로드할 파일을 찾을 수 없습니다.");
      return;
    }
    if (droppedFiles.length > 1) {
      setSelectedFile(null);
      setResult(null);
      setError("PDF 파일은 하나만 업로드할 수 있습니다.");
      return;
    }
    selectFile(droppedFiles[0]);
  };

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDragging(false);
    selectDroppedFiles(event.dataTransfer.files);
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedFile || isUploading) return;

    setIsUploading(true);
    setResult(null);
    setError(null);
    try {
      setResult(await uploadPolicy(selectedFile));
    } catch (err) {
      if (err instanceof UploadPolicyError) {
        setError(err.userMessage);
      } else {
        setError(err instanceof Error ? err.message : "업로드에 실패했습니다.");
      }
    } finally {
      setIsUploading(false);
    }
  };

  const fileSizeLabel = selectedFile
    ? `${(selectedFile.size / 1024 / 1024).toFixed(2)} MB`
    : "최대 10 MB";

  return (
    <form className="w-full max-w-xl" onSubmit={handleSubmit}>
      <section className="rounded-[8px] border border-zinc-200 bg-white shadow-[0_16px_60px_rgba(0,0,0,0.06)]">
        <div className="px-5 pt-6 pb-5 sm:px-7 sm:pt-7">
          <h1 className="text-2xl leading-8 font-semibold tracking-normal text-zinc-950">
            보험증권 업로드
          </h1>
          <p className="mt-2 text-sm leading-6 text-zinc-500">
            PDF 파일 하나를 올려주세요. 다음 단계에서 보장 내용을 읽습니다.
          </p>
        </div>

        <div className="px-5 pb-5 sm:px-7 sm:pb-7">
          <div
            data-testid="policy-upload-dropzone"
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
            className={`flex min-h-48 flex-col items-center justify-center rounded-[8px] border border-dashed px-5 py-10 text-center transition-colors ${
              isDragging
                ? "border-zinc-950 bg-zinc-100"
                : "border-zinc-300 bg-zinc-50"
            }`}
          >
            <p className="text-base font-medium text-zinc-950">
              파일을 끌어오거나 선택하세요
            </p>
            <p className="mt-2 text-sm text-zinc-500">PDF · {fileSizeLabel}</p>

            <input
              ref={inputRef}
              id="policy-file"
              className="sr-only"
              type="file"
              accept="application/pdf,.pdf"
              aria-label="PDF 파일 선택"
              onChange={(event) => selectFile(event.target.files?.[0])}
            />
            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              className="mt-6 rounded-[8px] bg-zinc-950 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-zinc-800 focus:ring-2 focus:ring-zinc-950 focus:ring-offset-2 focus:outline-none"
            >
              파일 선택
            </button>
          </div>

          <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              {selectedFile ? (
                <p className="truncate text-sm font-medium text-zinc-900">
                  {selectedFile.name}
                </p>
              ) : (
                <p className="text-sm text-zinc-500">선택된 파일 없음</p>
              )}
            </div>
            <button
              type="submit"
              disabled={!selectedFile || isUploading}
              className="rounded-[8px] bg-zinc-950 px-4 py-2.5 text-sm font-medium text-white transition-colors focus:ring-2 focus:ring-zinc-950 focus:ring-offset-2 focus:outline-none enabled:hover:bg-zinc-800 disabled:cursor-not-allowed disabled:bg-zinc-200 disabled:text-zinc-500"
            >
              {isUploading ? "업로드 중" : "업로드"}
            </button>
          </div>

          {result ? (
            <p className="mt-4 rounded-[8px] bg-[#eef8f1] px-4 py-3 text-sm leading-6 text-[#1f6f3f]">
              <span className="font-medium">업로드가 완료되었습니다.</span>
              <span className="block text-[#2f7f4e]">
                다음 단계에서 보장 내용을 읽습니다.
              </span>
            </p>
          ) : null}

          {error ? (
            <p
              role="alert"
              className="mt-4 rounded-[8px] bg-red-50 px-4 py-3 text-sm leading-6 text-red-700"
            >
              {error}
            </p>
          ) : null}
        </div>
      </section>
    </form>
  );
}
