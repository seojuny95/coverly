import { type DragEvent, type RefObject, useState } from "react";
import { PORTFOLIO_MAX_DOCUMENTS } from "@/shared/api/generated-runtime";
import { Button } from "@/shared/components/ui/button";
import { Card } from "@/shared/components/ui/card";
import type { SelectedPolicyFile, UploadSurface } from "../types";

export function PdfDropzone({
  files,
  existingDocumentCount,
  requiredInsuredPersonName,
  surface,
  disabled,
  inputRef,
  onSelectFiles,
}: {
  files: SelectedPolicyFile[];
  existingDocumentCount: number;
  requiredInsuredPersonName?: string;
  surface: UploadSurface;
  disabled: boolean;
  inputRef: RefObject<HTMLInputElement | null>;
  onSelectFiles: (files: FileList | File[]) => void;
}) {
  const [isDragging, setIsDragging] = useState(false);
  const isModal = surface === "modal";
  const remainingDocumentCount = Math.max(
    0,
    PORTFOLIO_MAX_DOCUMENTS - existingDocumentCount,
  );
  const uploadLimitLabel =
    existingDocumentCount > 0
      ? `추가 가능 ${remainingDocumentCount}개 · 전체 최대 ${PORTFOLIO_MAX_DOCUMENTS}개`
      : `최대 ${PORTFOLIO_MAX_DOCUMENTS}개`;
  const selectedBytes = files.reduce(
    (sum, selectedFile) => sum + selectedFile.file.size,
    0,
  );
  const fileSizeLabel =
    files.length > 0
      ? `${files.length}개 · ${(selectedBytes / 1024 / 1024).toFixed(2)} MB · ${uploadLimitLabel}`
      : `PDF · ${uploadLimitLabel}`;
  const dropzoneTitle = requiredInsuredPersonName
    ? `${requiredInsuredPersonName}(피보험자)의 보험증권 PDF만 올릴 수 있어요`
    : "보험증권 PDF를 올려주세요";

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDragging(false);
    onSelectFiles(event.dataTransfer.files);
  };

  return (
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
      <Card
        shadow="mist"
        className="relative mb-5 grid size-11 place-items-center rounded-xl"
      >
        <span className="grid grid-cols-2 gap-1" aria-hidden="true">
          <span className="size-1.5 bg-zinc-300" />
          <span className="size-1.5 bg-blue-600" />
          <span className="size-1.5 bg-zinc-300" />
          <span className="size-1.5 bg-zinc-300" />
        </span>
      </Card>
      <p className="relative text-base font-medium text-zinc-950">
        {dropzoneTitle}
      </p>
      {!isModal ? (
        <p className="relative mt-2 text-sm leading-6 text-zinc-500">
          {fileSizeLabel}
        </p>
      ) : (
        <p className="relative mt-1 text-xs text-zinc-400">{fileSizeLabel}</p>
      )}

      <input
        ref={inputRef}
        id="insurance-file"
        className="sr-only"
        type="file"
        accept="application/pdf,.pdf"
        multiple
        disabled={disabled}
        aria-label="PDF 파일 선택"
        onChange={(event) => {
          if (event.target.files) onSelectFiles(event.target.files);
        }}
      />
      <Button
        type="button"
        variant="outline"
        disabled={disabled}
        onClick={() => inputRef.current?.click()}
        className="relative mt-6"
      >
        PDF 불러오기
      </Button>
    </div>
  );
}
