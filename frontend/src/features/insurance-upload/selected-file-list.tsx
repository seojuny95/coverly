"use client";

import type { FileReadStatus, SelectedUploadFile } from "./upload-types";

// The list of PDFs the user has picked (before submitting), with per-file
// status/error badges and a remove button. Presentational: all state lives in
// the parent form; this only renders and reports removals.
export function SelectedFileList({
  files,
  surface,
  onRemove,
  disableRemove,
}: {
  files: SelectedUploadFile[];
  surface: "page" | "modal";
  onRemove: (fileId: string) => void;
  disableRemove: boolean;
}) {
  if (files.length === 0) {
    return (
      <div
        className={
          surface === "modal"
            ? "rounded-xl border border-zinc-200 bg-white px-4 py-4"
            : "rounded-xl border border-zinc-200 bg-white px-4 py-4"
        }
      >
        <p className="text-sm text-zinc-500">선택된 PDF가 없어요.</p>
      </div>
    );
  }

  return (
    <section
      aria-label="선택한 PDF"
      className={
        surface === "modal"
          ? "rounded-xl border border-zinc-200 bg-white px-4 py-4"
          : "rounded-xl border border-zinc-200 bg-white px-4 py-4"
      }
    >
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm font-semibold text-zinc-950">선택한 PDF</p>
        <p className="text-xs text-zinc-500">
          {files.length}개 ·{" "}
          {formatFileSize(
            files.reduce(
              (sum, selectedFile) => sum + selectedFile.file.size,
              0,
            ),
          )}
        </p>
      </div>
      <ul className="mt-3 space-y-2">
        {files.map((selectedFile) => (
          <li
            key={selectedFile.id}
            className={`flex items-start justify-between gap-3 rounded-lg border px-3 py-2 text-xs ${
              selectedFile.status === "failed"
                ? "border-red-200 bg-red-50 text-red-900"
                : "border-zinc-200 bg-zinc-50 text-zinc-700"
            }`}
          >
            <span className="min-w-0">
              <span className="flex min-w-0 flex-wrap items-center gap-2">
                <span className="inline-block max-w-[260px] truncate align-bottom font-medium">
                  {selectedFile.file.name}
                </span>
                <SelectedFileStatusBadge
                  status={selectedFile.status}
                  errorCode={selectedFile.errorCode}
                />
              </span>
              {selectedFile.errorMessage ? (
                <span className="mt-1 block leading-5 text-red-700">
                  {selectedFile.errorMessage}
                </span>
              ) : (
                <span className="mt-1 block text-zinc-500">
                  {formatFileSize(selectedFile.file.size)}
                </span>
              )}
            </span>
            <button
              type="button"
              disabled={disableRemove}
              onClick={() => onRemove(selectedFile.id)}
              aria-label={`${selectedFile.file.name} 제거`}
              className="shrink-0 rounded-md border border-zinc-200 bg-white px-2 py-1 font-medium text-zinc-600 transition-colors hover:border-zinc-300 hover:text-zinc-950 disabled:cursor-not-allowed disabled:opacity-50"
            >
              제거
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function failedBadgeLabel(errorCode?: string): string {
  if (errorCode === "INVALID_PDF") return "PDF 형식 아님";
  if (errorCode === "DUPLICATE_POLICY") return "중복 증권";
  return "읽을 수 없는 PDF";
}

function SelectedFileStatusBadge({
  status,
  errorCode,
}: {
  status: FileReadStatus;
  errorCode?: string;
}) {
  if (status === "failed") {
    return (
      <span className="rounded-md border border-red-200 bg-white px-1.5 py-0.5 text-[11px] font-semibold text-red-700">
        {failedBadgeLabel(errorCode)}
      </span>
    );
  }

  if (status === "done") {
    return (
      <span className="rounded-md border border-blue-100 bg-blue-50 px-1.5 py-0.5 text-[11px] font-semibold text-blue-700">
        완료
      </span>
    );
  }

  return null;
}

function formatFileSize(size: number) {
  if (size < 1024 * 1024) {
    return `${Math.max(size / 1024, 0.01).toFixed(2)} KB`;
  }

  return `${(size / 1024 / 1024).toFixed(2)} MB`;
}
