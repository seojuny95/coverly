"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { AnalyzedInsurance } from "../insurance-analysis/insurance-analysis-store";
import { PortfolioAnalysisResultView } from "./portfolio-analysis-result";
import {
  type PortfolioAnalysisResult,
  requestPortfolioAnalysis,
} from "./portfolio-api";

type Demographics = {
  age: number;
  gender: string;
  lifeStage?: string;
  source?: "policy" | "user" | "unknown";
};

export function PortfolioAnalysisPanel({
  active,
  documents,
}: {
  active: boolean;
  documents: AnalyzedInsurance[];
}) {
  const automaticDemographics = useMemo(
    () => findDemographics(documents),
    [documents],
  );
  const [manualDemographics, setManualDemographics] =
    useState<Demographics | null>(null);
  const demographics = automaticDemographics ?? manualDemographics;
  const [state, setState] = useState<{
    status: "idle" | "loading" | "success" | "error";
    result?: PortfolioAnalysisResult;
  }>({ status: "idle" });
  const [attempt, setAttempt] = useState(0);
  const requestedKey = useRef<string | null>(null);
  const requestSequence = useRef(0);
  const eligibleDocuments = useMemo(
    () =>
      documents.filter(
        ({ result }) => !result.기본정보?.보험분류?.includes("자동차"),
      ),
    [documents],
  );
  const portfolioKey = eligibleDocuments
    .map((document) => `${document.id}:${document.result.문자수}`)
    .join("|");

  useEffect(() => {
    if (!demographics) return;
    const requestKey = `${portfolioKey}:${demographics.age}:${demographics.gender}:${attempt}`;
    if (!active || requestedKey.current === requestKey) return;
    requestedKey.current = requestKey;
    requestSequence.current += 1;
    const requestId = requestSequence.current;
    setState({ status: "loading" });
    const controller = new AbortController();
    void requestPortfolioAnalysis(documents, demographics, controller.signal)
      .then((result) => {
        if (requestSequence.current === requestId)
          setState({ status: "success", result });
      })
      .catch((error: unknown) => {
        if (
          requestSequence.current === requestId &&
          (error as { name?: string }).name !== "AbortError"
        )
          setState({ status: "error" });
      });
    // Keep the request alive when the user switches tabs.
  }, [active, attempt, demographics, documents, portfolioKey]);

  if (eligibleDocuments.length === 0) {
    return (
      <InfoState
        title="분석할 일반 보험이 없어요"
        description="자동차보험은 이번 분석에서 제외해요. 건강·생명·운전자보험 증권을 올리면 상담 전 검토를 시작할 수 있어요."
      />
    );
  }

  if (!demographics) {
    return <DemographicsForm onSubmit={setManualDemographics} />;
  }

  if (state.status === "idle" || state.status === "loading")
    return <AnalysisLoading />;
  if (state.status === "error")
    return (
      <section className="rounded-2xl border border-zinc-200 p-8 text-center">
        <h2 className="text-xl font-semibold">분석 결과를 불러오지 못했어요</h2>
        <p className="mt-2 text-sm text-zinc-500">
          업로드한 증권은 그대로 있어요. 잠시 후 다시 확인해주세요.
        </p>
        <button
          type="button"
          className="mt-5 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white"
          onClick={() => {
            setState({ status: "idle" });
            setAttempt((value) => value + 1);
          }}
        >
          다시 분석하기
        </button>
      </section>
    );

  return <PortfolioAnalysisResultView result={state.result!} />;
}

function findDemographics(documents: AnalyzedInsurance[]): Demographics | null {
  const candidates = new Map<string, Demographics>();
  for (const document of documents) {
    if (document.result.기본정보?.보험분류?.includes("자동차")) continue;
    const info = document.result.기본정보?.피보험자정보;
    if (typeof info?.나이 === "number" && info.성별) {
      const demographics = {
        age: info.나이,
        gender: info.성별,
        lifeStage: info.생애단계,
        source: "policy",
      } satisfies Demographics;
      candidates.set(
        `${demographics.age}:${demographics.gender}`,
        demographics,
      );
    }
  }
  if (candidates.size !== 1) return null;
  return candidates.values().next().value ?? null;
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
        className="mt-6 rounded-lg bg-blue-600 px-5 py-3 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"
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
        상담 전에 볼 내용을 정리하고 있어요
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
