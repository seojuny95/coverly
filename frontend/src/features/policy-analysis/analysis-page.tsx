"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import {
  type AnalyzedPolicy,
  type PolicyAnalysis,
  loadPolicyAnalysis,
} from "./analysis-store";
import type {
  PolicyBasicInfo,
  PolicyPremium,
  PolicyPeriod,
} from "../policy-upload/upload-policy";

const CLASSIFICATION_ORDER = [
  "자동차",
  "상해·질병·실손",
  "생명·연금",
  "배상·화재·기타",
  "미분류",
];

export function AnalysisPage() {
  const [analysis, setAnalysis] = useState<PolicyAnalysis | null>();
  const [expandedPolicyIds, setExpandedPolicyIds] = useState<Set<string>>(
    () => new Set(),
  );

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      setAnalysis(loadPolicyAnalysis());
    }, 0);

    return () => window.clearTimeout(timeoutId);
  }, []);

  const policies = useMemo(() => analysis?.policies ?? [], [analysis]);
  const groupedPolicies = useMemo(() => groupPolicies(policies), [policies]);
  const counts = useMemo(() => countPolicies(policies), [policies]);

  const togglePolicy = (policyId: string) => {
    setExpandedPolicyIds((current) => {
      const next = new Set(current);
      if (next.has(policyId)) {
        next.delete(policyId);
      } else {
        next.add(policyId);
      }
      return next;
    });
  };

  if (analysis === undefined) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-white px-5 text-[#111827]">
        <p className="text-sm font-medium">분석 결과를 불러오는 중입니다.</p>
      </main>
    );
  }

  if (!analysis || policies.length === 0) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-white px-5 text-[#111827]">
        <section className="w-full max-w-lg rounded-[8px] border border-[#111827]/15 bg-white px-6 py-8 text-center shadow-[0_18px_70px_rgba(17,24,39,0.08)]">
          <h1 className="text-2xl font-semibold tracking-normal">
            분석할 증권이 없습니다
          </h1>
          <p className="mt-3 text-sm leading-6 text-[#111827]/70">
            업로드 화면에서 PDF를 선택하면 분석 결과가 여기에 표시됩니다.
          </p>
          <Link
            href="/upload"
            className="mt-6 inline-flex rounded-[8px] bg-[#111827] px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-[#111827]/90 focus:ring-2 focus:ring-[#2563EB] focus:ring-offset-2 focus:outline-none"
          >
            증권 업로드
          </Link>
        </section>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-white px-5 py-6 text-[#111827] sm:px-6">
      <header className="mx-auto flex w-full max-w-6xl items-center justify-between gap-4">
        <Link href="/" className="text-sm font-semibold text-[#111827]">
          Coverly
        </Link>
        <Link
          href="/upload"
          className="rounded-[8px] border border-[#111827]/15 px-3 py-2 text-sm font-medium text-[#111827] transition-colors hover:bg-[#111827]/5 focus:ring-2 focus:ring-[#2563EB] focus:ring-offset-2 focus:outline-none"
        >
          다시 업로드
        </Link>
      </header>

      <section className="mx-auto mt-10 w-full max-w-6xl">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h1 className="text-3xl font-semibold tracking-normal text-[#111827] sm:text-4xl">
              보험 분류별 분석
            </h1>
            <p className="mt-3 text-sm leading-6 text-[#111827]/70">
              {analysis.selectedName
                ? `${analysis.selectedName} 피보험자의 ${policies.length}개 증권을 보험분류 기준으로 정리했습니다.`
                : `${policies.length}개 증권을 보험분류 기준으로 정리했습니다.`}
            </p>
          </div>
          <p className="text-sm text-[#111827]/70">
            분석 시각 {formatDateTime(analysis.generatedAt)}
          </p>
        </div>

        <dl className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          {CLASSIFICATION_ORDER.map((classification) => (
            <div
              key={classification}
              className="rounded-[8px] border border-[#111827]/15 bg-white px-4 py-4"
            >
              <dt className="text-xs font-medium text-[#111827]/70">
                {classification}
              </dt>
              <dd className="mt-3 text-3xl font-semibold text-[#2563EB]">
                {counts[classification] ?? 0}
              </dd>
            </div>
          ))}
        </dl>

        <div className="mt-8 space-y-5">
          {CLASSIFICATION_ORDER.map((classification) => {
            const classificationPolicies =
              groupedPolicies[classification] ?? [];
            if (classificationPolicies.length === 0) return null;

            return (
              <section
                key={classification}
                className="overflow-hidden rounded-[8px] border border-[#111827]/15 bg-white"
              >
                <div className="border-b border-[#111827]/10 bg-white px-5 py-4">
                  <h2 className="text-lg font-semibold tracking-normal">
                    {classification}
                  </h2>
                  <p className="mt-1 text-sm text-[#111827]/70">
                    {classificationPolicies.length}개 증권
                  </p>
                </div>

                <ul className="divide-y divide-[#111827]/10">
                  {classificationPolicies.map((policy) => {
                    const isExpanded = expandedPolicyIds.has(policy.id);
                    const basicInfo = policy.result.기본정보;

                    return (
                      <li key={policy.id}>
                        <button
                          type="button"
                          aria-expanded={isExpanded}
                          onClick={() => togglePolicy(policy.id)}
                          className="flex w-full flex-col gap-3 px-5 py-4 text-left transition-colors hover:bg-[#111827]/5 focus:ring-2 focus:ring-[#2563EB] focus:outline-none focus:ring-inset sm:flex-row sm:items-center sm:justify-between"
                        >
                          <span className="min-w-0">
                            <span className="block truncate text-base font-semibold text-[#111827]">
                              {basicInfo?.상품명 ?? policy.fileName}
                            </span>
                            <span className="mt-1 block truncate text-sm text-[#111827]/70">
                              {basicInfo?.보험사 ?? "보험사 미확인"} ·{" "}
                              {policy.fileName}
                            </span>
                          </span>
                          <span className="inline-flex shrink-0 items-center rounded-full border border-[#2563EB]/20 px-3 py-1 text-xs font-medium text-[#2563EB]">
                            {isExpanded ? "접기" : "상세 보기"}
                          </span>
                        </button>

                        {isExpanded ? <PolicyDetail policy={policy} /> : null}
                      </li>
                    );
                  })}
                </ul>
              </section>
            );
          })}
        </div>
      </section>
    </main>
  );
}

function PolicyDetail({ policy }: { policy: AnalyzedPolicy }) {
  const basicInfo = policy.result.기본정보;
  const detailItems = [
    ["보험사", basicInfo?.보험사],
    ["상품명", basicInfo?.상품명],
    ["증권번호", basicInfo?.증권번호],
    ["계약자", basicInfo?.계약자],
    ["피보험자", basicInfo?.피보험자],
    ["보험기간", formatPeriod(basicInfo?.보험기간)],
    ["만기일", basicInfo?.만기일],
    ["납입기간", basicInfo?.납입기간],
    ["보험료", formatPremium(basicInfo?.보험료)],
    ["상품태그", basicInfo?.상품태그?.join(", ")],
  ].filter((item): item is [string, string] => Boolean(item[1]));

  return (
    <div className="border-t border-[#111827]/10 bg-[#111827]/5 px-5 py-5">
      <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {detailItems.map(([label, value]) => (
          <div key={label}>
            <dt className="text-xs font-medium text-[#111827]/70">{label}</dt>
            <dd className="mt-1 text-sm font-medium break-words text-[#111827]">
              {value}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function groupPolicies(policies: AnalyzedPolicy[]) {
  return policies.reduce<Record<string, AnalyzedPolicy[]>>((groups, policy) => {
    const classification = policy.result.기본정보?.보험분류 ?? "미분류";
    groups[classification] = [...(groups[classification] ?? []), policy];
    return groups;
  }, {});
}

function countPolicies(policies: AnalyzedPolicy[]) {
  return policies.reduce<Record<string, number>>((counts, policy) => {
    const classification = policy.result.기본정보?.보험분류 ?? "미분류";
    counts[classification] = (counts[classification] ?? 0) + 1;
    return counts;
  }, {});
}

function formatPeriod(period: PolicyPeriod | PolicyBasicInfo["보험기간"]) {
  if (!period?.시작일 || !period.종료일) return undefined;
  return `${period.시작일} - ${period.종료일}`;
}

function formatPremium(premium: PolicyPremium | PolicyBasicInfo["보험료"]) {
  if (premium?.금액 === undefined) return undefined;
  const cycle = premium.납입주기 ? `${premium.납입주기} ` : "";
  return `${cycle}${premium.금액.toLocaleString("ko-KR")}원`;
}

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}
