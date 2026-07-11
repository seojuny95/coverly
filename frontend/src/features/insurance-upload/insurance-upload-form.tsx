"use client";

import {
  type AnalyzedInsurance,
  type InsuranceAnalysis,
  getInsuredPersonName,
  saveInsuranceAnalysis,
} from "../insurance-analysis/insurance-analysis-store";
import {
  type DragEvent,
  type FormEvent,
  useEffect,
  useRef,
  useState,
} from "react";

import {
  type InsuranceUploadResult,
  UploadInsuranceError,
  uploadInsurance as uploadInsuranceRequest,
} from "./upload-insurance";
import {
  primaryButtonClassName,
  secondaryButtonClassName,
} from "../../components/coverly-brand";

export type UploadInsurance = (file: File) => Promise<InsuranceUploadResult>;

type InsuranceUploadFormProps = {
  uploadInsurance?: UploadInsurance;
  onAnalysisComplete?: (analysis: InsuranceAnalysis) => void;
  navigateToAnalysis?: () => void;
  fixedSelectedName?: string;
  surface?: "page" | "modal";
};

const MAX_PDF_BYTES = 10 * 1024 * 1024;

type FileReadStatus = "reading" | "done";

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
  onAnalysisComplete = saveInsuranceAnalysis,
  navigateToAnalysis = () => {
    window.location.assign("/analysis");
  },
  fixedSelectedName,
  surface = "page",
}: InsuranceUploadFormProps) {
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisProgress, setAnalysisProgress] = useState({
    completed: 0,
    total: 0,
  });
  const [fileStatuses, setFileStatuses] = useState<FileReadStatus[]>([]);
  const [pendingAnalysis, setPendingAnalysis] =
    useState<InsuranceAnalysis | null>(null);
  const [selectedName, setSelectedName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const selectFiles = (files: FileList | File[]) => {
    const incomingFiles = toFiles(files);
    if (incomingFiles.length === 0) {
      setSelectedFiles([]);
      setPendingAnalysis(null);
      setSelectedName("");
      setError("올릴 파일을 찾지 못했어요. PDF를 다시 선택해주세요.");
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
    setAnalysisProgress({ completed: 0, total: selectedFiles.length });
    setFileStatuses(selectedFiles.map(() => "reading"));
    setError(null);
    setPendingAnalysis(null);
    setSelectedName("");
    try {
      const insuranceDocuments = await Promise.all(
        selectedFiles.map(async (file, index) => {
          try {
            const result = await uploadInsurance(file);
            setAnalysisProgress((current) => ({
              ...current,
              completed: current.completed + 1,
            }));
            setFileStatuses((current) =>
              current.map((status, statusIndex) =>
                statusIndex === index ? "done" : status,
              ),
            );
            return {
              id: `${Date.now()}-${index}-${file.name}`,
              fileName: file.name,
              result,
            };
          } catch (err) {
            const message =
              err instanceof UploadInsuranceError
                ? err.userMessage
                : err instanceof Error
                  ? err.message
                  : "업로드에 실패했어요. 잠시 후 다시 시도해주세요.";
            throw new Error(message);
          }
        }),
      );
      const analysis = {
        generatedAt: new Date().toISOString(),
        insuranceDocuments,
      };
      continueWithNameValidation(analysis);
    } catch (err) {
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
      setIsAnalyzing(false);
    }
  };

  const continueWithNameValidation = (analysis: InsuranceAnalysis) => {
    const insuranceDocumentsWithoutName = analysis.insuranceDocuments.filter(
      (insuranceDocument) => !getInsuredPersonName(insuranceDocument),
    );
    if (insuranceDocumentsWithoutName.length > 0) {
      setError(
        "피보험자를 확인할 수 없는 증권이 있어요. 피보험자가 확인된 증권만 분석할 수 있어요.",
      );
      return;
    }

    if (fixedSelectedName) {
      const names = getInsuranceNameOptions(analysis.insuranceDocuments).map(
        (option) => option.name,
      );
      if (names.length > 1 || names[0] !== fixedSelectedName) {
        setError(
          `${fixedSelectedName}님의 보험증권만 추가할 수 있어요. 같은 피보험자의 증권만 선택해주세요.`,
        );
        return;
      }

      saveSelectedNameAnalysis(analysis, fixedSelectedName);
      return;
    }

    const names = getInsuranceNameOptions(analysis.insuranceDocuments).map(
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
        files={selectedFiles.map((file, index) => ({
          name: file.name,
          status: fileStatuses[index] ?? "reading",
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
            <SelectedFileList files={selectedFiles} surface={surface} />
            <button
              type="submit"
              disabled={selectedFiles.length === 0 || isAnalyzing}
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

function SelectedFileList({
  files,
  surface,
}: {
  files: File[];
  surface: "page" | "modal";
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

  const visibleFiles = files.slice(0, 6);
  const hiddenFileCount = Math.max(files.length - visibleFiles.length, 0);

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
          {formatFileSize(files.reduce((sum, file) => sum + file.size, 0))}
        </p>
      </div>
      <ul className="mt-3 flex flex-wrap gap-2">
        {visibleFiles.map((file, index) => (
          <li
            key={`${file.name}-${file.size}-${index}`}
            className="max-w-full rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-1.5 text-xs font-medium text-zinc-700"
          >
            <span className="inline-block max-w-[220px] truncate align-bottom">
              {file.name}
            </span>
          </li>
        ))}
        {hiddenFileCount > 0 ? (
          <li className="rounded-lg border border-blue-100 bg-blue-50 px-3 py-1.5 text-xs font-medium text-blue-700">
            외 {hiddenFileCount}개
          </li>
        ) : null}
      </ul>
    </section>
  );
}

const ANALYSIS_STEP_MESSAGES = [
  "증권에서 보장 내용을 찾고 있어요",
  "보장마다 확인한 근거를 붙이고 있어요",
];

const LONG_WAIT_MESSAGE = "파일이 길수록 조금 더 걸려요. 지금도 읽고 있어요.";
const ALMOST_DONE_MESSAGE = "거의 다 왔어요. 조금만 더 기다려주세요.";

function AnalysisProgress({
  progress,
  files,
  surface,
}: {
  progress: { completed: number; total: number };
  files: Array<{ name: string; status: FileReadStatus }>;
  surface: "page" | "modal";
}) {
  const milestonePercent =
    progress.total > 0 ? (progress.completed / progress.total) * 100 : 0;
  // Trickle only fills up to 90% of the in-flight file's share; real
  // completions move the milestone, so the bar never fakes a finish.
  const trickleCapPercent =
    progress.total > 0
      ? Math.min(((progress.completed + 0.9) / progress.total) * 100, 100)
      : 90;
  const [displayPercent, setDisplayPercent] = useState(0);
  const [messageIndex, setMessageIndex] = useState(0);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setDisplayPercent(
        (current) => current + (trickleCapPercent - current) * 0.04,
      );
    }, 250);
    return () => clearInterval(timer);
  }, [trickleCapPercent]);

  useEffect(() => {
    const timer = setInterval(() => {
      setMessageIndex((current) => current + 1);
    }, 4000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    const timer = setInterval(() => {
      setElapsedSeconds((current) => current + 1);
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  const statusMessages = [
    ...ANALYSIS_STEP_MESSAGES,
    ...(elapsedSeconds >= 90
      ? [ALMOST_DONE_MESSAGE]
      : elapsedSeconds >= 30
        ? [LONG_WAIT_MESSAGE]
        : []),
  ];
  const statusMessage = statusMessages[messageIndex % statusMessages.length];
  // Real milestones floor the trickle so completed files always show through.
  const percent = Math.round(Math.max(displayPercent, milestonePercent));

  return (
    <section
      role="status"
      className={`${
        surface === "modal"
          ? "flex w-full max-w-none flex-col items-center py-8 text-center"
          : "fixed inset-0 z-50 flex items-center justify-center bg-white/90 px-6 py-10 text-center backdrop-blur-sm"
      }`}
    >
      <div className="flex w-full max-w-[560px] flex-col items-center">
        <div className="analysis-pixel-loader grid size-16 grid-cols-3 gap-1.5 rounded-2xl border border-zinc-200 bg-white p-3 shadow-[7px_7px_0_#e8edff]">
          {Array.from({ length: 9 }).map((_, index) => (
            <span key={index} />
          ))}
        </div>
        <h1 className="mt-8 text-2xl font-semibold tracking-[-0.04em] text-zinc-950">
          증권을 한 장씩 읽고 있어요
        </h1>
        <p className="mt-2 text-sm leading-6 text-zinc-500">
          보통 1~2분 정도 걸려요
        </p>
        <div
          role="progressbar"
          aria-label="보험 분석 진행률"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={percent}
          className="mt-7 h-1.5 w-full overflow-hidden rounded-sm bg-zinc-100"
        >
          <div
            className="h-full bg-blue-600 transition-all duration-300"
            style={{ width: `${Math.max(percent, 4)}%` }}
          />
        </div>
        {files.length > 0 ? (
          <ul
            aria-label="파일별 진행 상태"
            className="mt-5 max-h-40 w-full space-y-1.5 overflow-y-auto text-left"
          >
            {files.map((file, index) => (
              <li
                key={`${file.name}-${index}`}
                className="flex items-center justify-between gap-3 rounded-lg border border-zinc-100 bg-white px-3 py-2 text-xs text-zinc-600"
              >
                <span className="truncate">{file.name}</span>
                {file.status === "done" ? (
                  <span className="shrink-0 font-medium text-blue-600">
                    완료
                  </span>
                ) : (
                  <span className="shrink-0 animate-pulse text-zinc-400">
                    읽는 중
                  </span>
                )}
              </li>
            ))}
          </ul>
        ) : null}
        <p
          key={statusMessage}
          className="analysis-status-message mt-6 text-sm leading-6 text-zinc-500"
        >
          {statusMessage}
        </p>
        <p className="mt-1 text-xs text-zinc-400">
          확인이 안 되는 내용은 추측하지 않아요.
        </p>
      </div>
    </section>
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

function formatFileSize(size: number) {
  if (size < 1024 * 1024) {
    return `${Math.max(size / 1024, 0.01).toFixed(2)} KB`;
  }

  return `${(size / 1024 / 1024).toFixed(2)} MB`;
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
