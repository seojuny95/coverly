"use client";

import {
  type AnalyzedPolicy,
  type PolicyAnalysis,
  getPolicyPersonName,
  savePolicyAnalysis,
} from "../policy-analysis/analysis-store";
import { type DragEvent, type FormEvent, useRef, useState } from "react";

import {
  type PolicyUploadResult,
  UploadPolicyError,
  uploadPolicy as uploadPolicyRequest,
} from "./upload-policy";

export type UploadPolicy = (file: File) => Promise<PolicyUploadResult>;

type UploadFormProps = {
  uploadPolicy?: UploadPolicy;
  onAnalysisComplete?: (analysis: PolicyAnalysis) => void;
  navigateToAnalysis?: () => void;
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
  onAnalysisComplete = savePolicyAnalysis,
  navigateToAnalysis = () => {
    window.location.assign("/analysis");
  },
}: UploadFormProps) {
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [pendingAnalysis, setPendingAnalysis] = useState<PolicyAnalysis | null>(
    null,
  );
  const [selectedName, setSelectedName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const selectFiles = (files: FileList | File[]) => {
    const incomingFiles = toFiles(files);
    if (incomingFiles.length === 0) {
      setSelectedFiles([]);
      setPendingAnalysis(null);
      setSelectedName("");
      setError("업로드할 파일을 찾을 수 없습니다.");
      return;
    }

    const invalidFile = incomingFiles.find((file) => validateFile(file));
    if (invalidFile) {
      const validationError = validateFile(invalidFile);
      setSelectedFiles([]);
      setPendingAnalysis(null);
      setSelectedName("");
      setError(validationError);
      if (inputRef.current) inputRef.current.value = "";
      return;
    }

    setSelectedFiles(incomingFiles);
    setPendingAnalysis(null);
    setSelectedName("");
    setError(null);
  };

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDragging(false);
    selectFiles(event.dataTransfer.files);
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (selectedFiles.length === 0 || isAnalyzing) return;

    setIsAnalyzing(true);
    setError(null);
    setPendingAnalysis(null);
    setSelectedName("");
    try {
      const policies = await Promise.all(
        selectedFiles.map(async (file, index) => {
          try {
            return {
              id: `${Date.now()}-${index}-${file.name}`,
              fileName: file.name,
              result: await uploadPolicy(file),
            };
          } catch (err) {
            const message =
              err instanceof UploadPolicyError
                ? err.userMessage
                : err instanceof Error
                  ? err.message
                  : "업로드에 실패했습니다.";
            throw new Error(`${file.name}: ${message}`);
          }
        }),
      );
      const analysis = {
        generatedAt: new Date().toISOString(),
        policies,
      };
      continueWithNameValidation(analysis);
    } catch (err) {
      if (err instanceof UploadPolicyError) {
        setError(err.userMessage);
      } else {
        setError(err instanceof Error ? err.message : "업로드에 실패했습니다.");
      }
    } finally {
      setIsAnalyzing(false);
    }
  };

  const continueWithNameValidation = (analysis: PolicyAnalysis) => {
    const policiesWithoutName = analysis.policies.filter(
      (policy) => !getPolicyPersonName(policy),
    );
    if (policiesWithoutName.length > 0) {
      const fileNames = policiesWithoutName
        .map((policy) => policy.fileName)
        .join(", ");
      setError(
        `피보험자를 확인할 수 없는 증권이 있습니다: ${fileNames}. 피보험자가 있는 증권만 분석할 수 있습니다.`,
      );
      return;
    }

    const names = getPolicyNameOptions(analysis.policies).map(
      (option) => option.name,
    );
    if (names.length === 1) {
      saveSelectedNameAnalysis(analysis, names[0]);
      return;
    }

    setSelectedName(names[0] ?? "");
    setPendingAnalysis(analysis);
  };

  const saveSelectedNameAnalysis = (
    analysis: PolicyAnalysis,
    personName: string,
  ) => {
    const filteredAnalysis = {
      ...analysis,
      selectedName: personName,
      policies: analysis.policies.filter(
        (policy) => getPolicyPersonName(policy) === personName,
      ),
    };
    onAnalysisComplete(filteredAnalysis);
    navigateToAnalysis();
  };

  const handleNameSelectionSubmit = () => {
    if (!pendingAnalysis || !selectedName) return;
    saveSelectedNameAnalysis(pendingAnalysis, selectedName);
  };

  const selectedBytes = selectedFiles.reduce((sum, file) => sum + file.size, 0);
  const fileSizeLabel =
    selectedFiles.length > 0
      ? `${selectedFiles.length}개 · ${(selectedBytes / 1024 / 1024).toFixed(2)} MB`
      : "파일당 최대 10 MB";

  return (
    <form className="w-full max-w-2xl" onSubmit={handleSubmit}>
      <section className="rounded-[8px] border border-[#d7ddd8] bg-[#fbfcfa] shadow-[0_18px_70px_rgba(25,45,33,0.08)]">
        <div className="px-5 pt-6 pb-5 sm:px-7 sm:pt-7">
          <h1 className="text-2xl leading-8 font-semibold tracking-normal text-[#152217]">
            내 보험 분석
          </h1>
          <p className="mt-2 text-sm leading-6 text-[#667269]">
            보험증권 PDF를 올리면 내 보험을 분류해서 보여드려요.
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
                ? "border-[#173d27] bg-[#eef8f1]"
                : "border-[#bec9c0] bg-white"
            }`}
          >
            <p className="text-base font-medium text-[#152217]">
              보험증권 PDF를 올려주세요
            </p>
            <p className="mt-2 text-sm text-[#667269]">PDF · {fileSizeLabel}</p>

            <input
              ref={inputRef}
              id="policy-file"
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
              className="mt-6 rounded-[8px] bg-[#173d27] px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-[#255436] focus:ring-2 focus:ring-[#173d27] focus:ring-offset-2 focus:outline-none"
            >
              PDF 불러오기
            </button>
          </div>

          <div className="mt-4 flex flex-col gap-4">
            <SelectedFileList files={selectedFiles} />
            <button
              type="submit"
              disabled={selectedFiles.length === 0 || isAnalyzing}
              className="self-stretch rounded-[8px] bg-[#173d27] px-4 py-2.5 text-sm font-medium text-white transition-colors focus:ring-2 focus:ring-[#173d27] focus:ring-offset-2 focus:outline-none enabled:hover:bg-[#255436] disabled:cursor-not-allowed disabled:bg-[#dfe5df] disabled:text-[#77847b] sm:self-end"
            >
              {isAnalyzing ? "분석 중" : "내 보험 분석하기"}
            </button>
          </div>

          {isAnalyzing ? (
            <div
              role="status"
              className="mt-4 rounded-[8px] border border-[#cfe0d2] bg-[#eef8f1] px-4 py-3 text-sm leading-6 text-[#1f6f3f]"
            >
              <span className="font-medium">보험을 정리하고 있어요.</span>
              <span className="block text-[#2f7f4e]">
                끝나면 결과 화면으로 이동해요.
              </span>
            </div>
          ) : null}

          {pendingAnalysis ? (
            <NameSelectionPanel
              options={getPolicyNameOptions(pendingAnalysis.policies)}
              selectedName={selectedName}
              onSelectedNameChange={setSelectedName}
              onContinue={handleNameSelectionSubmit}
            />
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

function SelectedFileList({ files }: { files: File[] }) {
  if (files.length === 0) {
    return (
      <div className="rounded-[8px] border border-[#e0e7df] bg-white px-4 py-3">
        <p className="text-sm text-[#667269]">선택된 PDF가 없어요.</p>
      </div>
    );
  }

  return (
    <section
      aria-label="선택한 PDF"
      className="rounded-[8px] border border-[#d7ddd8] bg-white"
    >
      <div className="flex items-center justify-between border-b border-[#e5ebe3] px-4 py-3">
        <p className="text-sm font-semibold text-[#152217]">선택한 PDF</p>
        <p className="text-xs font-medium text-[#667269]">{files.length}개</p>
      </div>
      <ul className="max-h-48 divide-y divide-[#edf1eb] overflow-y-auto">
        {files.map((file, index) => (
          <li
            key={`${file.name}-${file.size}-${index}`}
            className="flex min-h-16 items-center gap-3 px-4 py-3"
          >
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[8px] bg-[#eef8f1] text-xs font-semibold text-[#1f6f3f]">
              {index + 1}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium text-[#203226]">
                {file.name}
              </span>
              <span className="mt-1 block text-xs text-[#667269]">
                {formatFileSize(file.size)}
              </span>
            </span>
            <span className="shrink-0 rounded-full border border-[#d6e8db] px-2.5 py-1 text-xs font-medium text-[#2f7f4e]">
              PDF
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function formatFileSize(size: number) {
  if (size < 1024 * 1024) {
    return `${Math.max(size / 1024, 0.01).toFixed(2)} KB`;
  }

  return `${(size / 1024 / 1024).toFixed(2)} MB`;
}

function getPolicyNameOptions(policies: AnalyzedPolicy[]) {
  const counts = new Map<string, number>();
  for (const policy of policies) {
    const personName = getPolicyPersonName(policy);
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
    <div className="mt-4 rounded-[8px] border border-[#d7ddd8] bg-white px-4 py-4">
      <p className="text-sm font-semibold text-[#152217]">
        피보험자가 여러 명 발견되었습니다
      </p>
      <p className="mt-1 text-sm leading-6 text-[#667269]">
        분석에 포함할 피보험자를 선택하세요. 선택한 피보험자의 증권만 결과
        화면에 표시됩니다.
      </p>

      <div className="mt-4 grid gap-2">
        {options.map((option, index) => {
          const inputId = `policy-person-name-${index}`;
          return (
            <label
              key={option.name}
              htmlFor={inputId}
              className={`flex cursor-pointer items-center justify-between rounded-[8px] border px-3 py-3 text-sm transition-colors ${
                selectedName === option.name
                  ? "border-[#173d27] bg-[#eef8f1]"
                  : "border-[#d7ddd8] bg-white hover:bg-[#f6f8f5]"
              }`}
            >
              <span className="flex items-center gap-3">
                <input
                  id={inputId}
                  type="radio"
                  name="policy-person-name"
                  value={option.name}
                  checked={selectedName === option.name}
                  onChange={(event) => onSelectedNameChange(event.target.value)}
                  className="h-4 w-4 accent-[#173d27]"
                />
                <span className="font-medium text-[#203226]">
                  {option.name}
                </span>
              </span>
              <span className="text-[#667269]">{option.count}개</span>
            </label>
          );
        })}
      </div>

      <button
        type="button"
        onClick={onContinue}
        disabled={!selectedName}
        className="mt-4 rounded-[8px] bg-[#173d27] px-4 py-2.5 text-sm font-medium text-white transition-colors focus:ring-2 focus:ring-[#173d27] focus:ring-offset-2 focus:outline-none enabled:hover:bg-[#255436] disabled:cursor-not-allowed disabled:bg-[#dfe5df] disabled:text-[#77847b]"
      >
        선택한 피보험자로 보기
      </button>
    </div>
  );
}
