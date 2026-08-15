import { LoaderCircle } from "lucide-react";

import { Button } from "@/shared/components/ui/button";
import { Card } from "@/shared/components/ui/card";
import { cn } from "@/shared/lib/utils";
import type { SampleLoadingStep } from "./use-sample-portfolio";

const LOADING_STEPS: {
  step: Exclude<SampleLoadingStep, "idle">;
  label: string;
}[] = [
  { step: "checking", label: "분석 서버 연결 확인" },
  { step: "creating", label: "샘플 분석 불러오기" },
  { step: "navigating", label: "분석 화면으로 이동" },
];

const LOADING_COPY: Record<
  Exclude<SampleLoadingStep, "idle">,
  { title: string; description: string; button: string }
> = {
  checking: {
    title: "샘플 분석을 열 준비를 하고 있어요",
    description: "서버가 깨어나는 중이면 잠시 걸릴 수 있어요.",
    button: "서버 연결 확인 중",
  },
  creating: {
    title: "미리 준비한 샘플 분석을 불러오고 있어요",
    description: "PDF를 다시 분석하지 않고 샘플 세션만 새로 만들고 있어요.",
    button: "샘플 불러오는 중",
  },
  navigating: {
    title: "분석 화면으로 이동하고 있어요",
    description: "내 보험, 보험 분석, AI 상담을 바로 확인할 수 있어요.",
    button: "분석 화면 여는 중",
  },
};

export function SamplePortfolioOption({
  disabled,
  error,
  loadingStep,
  onOpen,
}: {
  disabled: boolean;
  error: string | null;
  loadingStep: SampleLoadingStep;
  onOpen: () => void;
}) {
  const isLoading = loadingStep !== "idle";
  const loadingCopy = isLoading ? LOADING_COPY[loadingStep] : null;

  return (
    <Card
      shadow="zinc"
      aria-busy={isLoading}
      className={cn(
        "rounded-2xl border-zinc-200 p-5 transition-colors sm:p-6",
        isLoading ? "border-blue-200 bg-blue-50/40" : null,
      )}
    >
      <div className="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-base font-medium text-zinc-950">
            {loadingCopy?.title ?? "보험증권이 없어도 둘러볼 수 있어요"}
          </p>
          <p className="mt-1 text-sm leading-6 text-zinc-500">
            {loadingCopy?.description ??
              "미리 준비한 가상 보험 4개로 분석과 AI 상담을 체험해보세요. 실제 내 보험 데이터와 섞이지 않아요."}
          </p>
        </div>
        <Button
          type="button"
          variant="outline"
          className="shrink-0"
          aria-busy={isLoading}
          disabled={disabled || isLoading}
          onClick={onOpen}
        >
          {isLoading ? (
            <LoaderCircle aria-hidden="true" className="size-4 animate-spin" />
          ) : null}
          {loadingCopy?.button ?? "샘플 보험으로 둘러보기"}
        </Button>
      </div>

      {isLoading ? <SampleLoadingProgress currentStep={loadingStep} /> : null}
      {error ? (
        <p role="alert" className="mt-4 text-sm text-red-600">
          {error}
        </p>
      ) : null}
    </Card>
  );
}

function SampleLoadingProgress({
  currentStep,
}: {
  currentStep: Exclude<SampleLoadingStep, "idle">;
}) {
  const currentIndex = LOADING_STEPS.findIndex(
    ({ step }) => step === currentStep,
  );

  return (
    <div role="status" aria-live="polite" className="mt-5">
      <div className="h-1.5 overflow-hidden rounded-full bg-blue-100">
        <div
          className="h-full rounded-full bg-blue-600 transition-all duration-300"
          style={{
            width: `${((currentIndex + 1) / LOADING_STEPS.length) * 100}%`,
          }}
        />
      </div>
      <ol className="mt-3 grid gap-2 text-sm text-zinc-500 sm:grid-cols-3">
        {LOADING_STEPS.map(({ step, label }, index) => {
          const isDone = index < currentIndex;
          const isCurrent = index === currentIndex;

          return (
            <li
              key={step}
              className={cn(
                "flex items-center gap-2",
                isCurrent || isDone ? "text-blue-700" : null,
              )}
            >
              <span
                aria-hidden="true"
                className={cn(
                  "size-2 rounded-full bg-zinc-300",
                  isDone || isCurrent ? "bg-blue-600" : null,
                  isCurrent ? "animate-pulse" : null,
                )}
              />
              {label}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
