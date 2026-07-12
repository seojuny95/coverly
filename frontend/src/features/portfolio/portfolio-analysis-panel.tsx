"use client";

import { useState } from "react";
import { primaryButtonClassName } from "../../components/coverly-brand";
import type { EmptyReason } from "./analysis-eligibility";
import { PortfolioAnalysisResultView } from "./portfolio-analysis-result";
import type { Demographics } from "./use-portfolio-analysis";
import type { PortfolioAnalysisResult } from "./portfolio-api";

// Empty-state copy by reason: name what is empty, then the next action.
const EMPTY_COPY: Record<EmptyReason, { title: string; description: string }> =
  {
    "auto-only": {
      title: "분석할 보험이 없어요",
      description:
        "자동차보험은 이번 분석에서 제외해요. 건강·생명·운전자보험 증권을 올리면 검토를 시작할 수 있어요.",
    },
    "no-coverage": {
      title: "분석할 보험이 없어요",
      description:
        "담보 내용이 확인된 증권만 분석할 수 있어요. 담보가 담긴 증권을 올리면 검토를 시작할 수 있어요.",
    },
    mixed: {
      title: "분석할 보험이 없어요",
      description:
        "담보 내용이 확인된 증권만 분석할 수 있어요. 자동차보험은 제외하고, 담보가 담긴 증권을 올리면 검토를 시작할 수 있어요.",
    },
  };

export function PortfolioAnalysisPanel({
  status,
  result,
  eligibleCount,
  emptyReason,
  needsDemographics,
  onManualDemographics,
  onRetry,
}: {
  status: "idle" | "loading" | "success" | "error";
  result?: PortfolioAnalysisResult;
  eligibleCount: number;
  emptyReason: EmptyReason;
  needsDemographics: boolean;
  onManualDemographics: (value: Demographics) => void;
  onRetry: () => void;
}) {
  if (eligibleCount === 0) {
    return <InfoState {...EMPTY_COPY[emptyReason]} />;
  }

  if (needsDemographics) {
    return <DemographicsForm onSubmit={onManualDemographics} />;
  }

  if (status === "idle" || status === "loading") return <AnalysisLoading />;

  if (status === "error")
    return (
      <section className="rounded-2xl border border-zinc-200 p-8 text-center">
        <h2 className="text-xl font-semibold">분석 결과를 불러오지 못했어요</h2>
        <p className="mt-2 text-sm text-zinc-500">
          업로드한 증권은 그대로 있어요. 잠시 후 다시 확인해주세요.
        </p>
        <button
          type="button"
          className={`mt-5 ${primaryButtonClassName}`}
          onClick={onRetry}
        >
          다시 분석하기
        </button>
      </section>
    );

  return <PortfolioAnalysisResultView result={result!} />;
}

function DemographicsForm({
  onSubmit,
}: {
  onSubmit: (value: Demographics) => void;
}) {
  const [age, setAge] = useState("");
  const [gender, setGender] = useState("미상");

  return (
    <section className="rounded-2xl border border-zinc-200 p-6 sm:p-8">
      <h2 className="text-xl font-semibold">분석 기준을 확인해주세요</h2>
      <p className="mt-2 text-sm leading-6 text-zinc-500">
        증권에서 나이와 성별을 확인하지 못했어요. 입력한 정보는 이번 분석
        기준으로만 사용해요.
      </p>
      <div className="mt-6 grid gap-4 sm:grid-cols-2">
        <label className="text-sm font-medium">
          나이
          <input
            aria-label="나이"
            type="number"
            min={0}
            max={120}
            value={age}
            onChange={(event) => setAge(event.target.value)}
            className="mt-2 w-full rounded-xl border border-zinc-300 px-4 py-3 font-normal outline-none focus:border-blue-600"
            placeholder="예: 35"
          />
        </label>
        <label className="text-sm font-medium">
          성별
          <select
            aria-label="성별"
            value={gender}
            onChange={(event) => setGender(event.target.value)}
            className="mt-2 w-full rounded-xl border border-zinc-300 bg-white px-4 py-3 font-normal outline-none focus:border-blue-600"
          >
            <option value="미상">선택하지 않음</option>
            <option value="여성">여성</option>
            <option value="남성">남성</option>
            <option value="기타">기타</option>
          </select>
        </label>
      </div>
      <button
        type="button"
        disabled={!age}
        onClick={() => {
          const parsedAge = Number(age);
          if (Number.isInteger(parsedAge) && parsedAge >= 0 && parsedAge <= 120)
            onSubmit({ age: parsedAge, gender, source: "user" });
        }}
        className={`mt-6 ${primaryButtonClassName}`}
      >
        내 보험 분석하기
      </button>
    </section>
  );
}

function AnalysisLoading() {
  return (
    <section
      aria-live="polite"
      aria-busy="true"
      className="rounded-2xl border border-zinc-200 p-8"
    >
      <div className="h-2 w-20 animate-pulse rounded bg-blue-600" />
      <h2 className="mt-5 text-xl font-semibold">
        당신 편에서 보험을 살펴보고 있어요
      </h2>
      <p className="mt-2 text-sm leading-6 text-zinc-500">
        강점과 확인할 공백, 다음 질문을 증권 근거와 함께 살펴보고 있어요.
      </p>
      <div className="mt-7 grid gap-4 md:grid-cols-2">
        {[1, 2, 3, 4].map((item) => (
          <div
            key={item}
            className="h-32 animate-pulse rounded-xl bg-zinc-100"
          />
        ))}
      </div>
    </section>
  );
}

function InfoState({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <section className="rounded-2xl border border-zinc-200 p-8 text-center">
      <h2 className="text-xl font-semibold">{title}</h2>
      <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-zinc-500">
        {description}
      </p>
    </section>
  );
}
