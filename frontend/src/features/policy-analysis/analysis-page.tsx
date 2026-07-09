"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import insurerLogos from "./insurer-logos.json";
import {
  type AnalyzedPolicy,
  type PolicyAnalysis,
  getPolicyPersonName,
  loadPolicyAnalysis,
  savePolicyAnalysis,
} from "./analysis-store";
import type {
  PolicyBasicInfo,
  PolicyPremium,
  PolicyPeriod,
} from "../policy-upload/upload-policy";
import { UploadForm, type UploadPolicy } from "../policy-upload/upload-form";
import { PolicyCoverageList } from "./policy-coverage-list";

const CLASSIFICATION_ORDER = [
  "자동차",
  "상해·질병·실손",
  "생명·연금",
  "배상·화재·기타",
  "미분류",
];

const TAG_STYLES: Record<string, string> = {
  자동차: "border-[#2563EB]/10 bg-[#2563EB]/[0.06] text-[#111827]/60",
  실손: "border-[#2563EB]/10 bg-[#2563EB]/[0.06] text-[#111827]/60",
  암: "border-[#DC2626]/10 bg-[#DC2626]/[0.06] text-[#111827]/60",
  상해: "border-[#EA580C]/10 bg-[#EA580C]/[0.06] text-[#111827]/60",
  질병: "border-[#0891B2]/10 bg-[#0891B2]/[0.06] text-[#111827]/60",
  간병: "border-[#7C3AED]/10 bg-[#7C3AED]/[0.06] text-[#111827]/60",
  운전자: "border-[#2563EB]/10 bg-[#2563EB]/[0.06] text-[#111827]/60",
  화재: "border-[#F97316]/10 bg-[#F97316]/[0.06] text-[#111827]/60",
  배상책임: "border-[#0F766E]/10 bg-[#0F766E]/[0.06] text-[#111827]/60",
  종신: "border-[#4F46E5]/10 bg-[#4F46E5]/[0.06] text-[#111827]/60",
  정기: "border-[#6366F1]/10 bg-[#6366F1]/[0.06] text-[#111827]/60",
  연금: "border-[#0284C7]/10 bg-[#0284C7]/[0.06] text-[#111827]/60",
  어린이: "border-[#DB2777]/10 bg-[#DB2777]/[0.06] text-[#111827]/60",
};

const INSURER_LOGOS = insurerLogos;

type AnalysisPageProps = {
  uploadPolicy?: UploadPolicy;
};

export function AnalysisPage({ uploadPolicy }: AnalysisPageProps = {}) {
  const [analysis, setAnalysis] = useState<PolicyAnalysis | null>();
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
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

  const openUploadModal = () => setIsUploadModalOpen(true);
  const closeUploadModal = () => setIsUploadModalOpen(false);

  const handleAdditionalAnalysisComplete = (nextAnalysis: PolicyAnalysis) => {
    if (!analysis) return;

    const mergedAnalysis = mergePolicyAnalysis(analysis, nextAnalysis);
    savePolicyAnalysis(mergedAnalysis);
    setAnalysis(mergedAnalysis);
  };

  if (analysis === undefined) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-white px-5 text-[#111827]">
        <p className="text-sm font-medium">분석 결과를 불러오고 있어요.</p>
      </main>
    );
  }

  if (!analysis || policies.length === 0) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-white px-5 text-[#111827]">
        <section className="w-full max-w-lg rounded-[8px] border border-[#111827]/15 bg-white px-6 py-8 text-center shadow-[0_18px_70px_rgba(17,24,39,0.08)]">
          <h1 className="text-2xl font-semibold tracking-normal">
            분석할 보험증권이 없어요
          </h1>
          <p className="mt-3 text-sm leading-6 text-[#111827]/70">
            보험증권 PDF를 올리면 정리한 결과를 여기에서 볼 수 있어요.
          </p>
          <Link
            href="/upload"
            className="mt-6 inline-flex rounded-[8px] bg-[#111827] px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-[#111827]/90 focus:ring-2 focus:ring-[#2563EB] focus:ring-offset-2 focus:outline-none"
          >
            보험증권 올리기
          </Link>
        </section>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-white px-5 py-6 text-[#111827] sm:px-6">
      <header className="mx-auto flex w-full max-w-6xl items-center gap-4">
        <Link href="/" className="text-sm font-semibold text-[#111827]">
          Coverly
        </Link>
      </header>

      <section className="mx-auto mt-10 w-full max-w-6xl">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h1 className="text-3xl font-semibold tracking-normal text-[#111827] sm:text-4xl">
              내 보험을 종류별로 정리했어요
            </h1>
            <p className="mt-3 text-sm leading-6 text-[#111827]/70">
              {analysis.selectedName
                ? `${analysis.selectedName}님의 보험 ${policies.length}개를 종류별로 보기 쉽게 정리했어요.`
                : `보험 ${policies.length}개를 종류별로 보기 쉽게 정리했어요.`}
            </p>
          </div>
          <div className="flex flex-col items-start gap-3 sm:items-end">
            <button
              type="button"
              onClick={openUploadModal}
              className="rounded-[8px] bg-[#111827] px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-[#111827]/90 focus:ring-2 focus:ring-[#2563EB] focus:ring-offset-2 focus:outline-none"
            >
              보험증권 더 올리기
            </button>
            <p className="text-sm text-[#111827]/70">
              정리한 시각 {formatDateTime(analysis.generatedAt)}
            </p>
          </div>
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
                    보험 {classificationPolicies.length}개
                  </p>
                </div>

                <ul className="divide-y divide-[#111827]/10">
                  {classificationPolicies.map((policy) => {
                    const isExpanded = expandedPolicyIds.has(policy.id);
                    const basicInfo = policy.result.기본정보;

                    return (
                      <li key={policy.id}>
                        <div className="overflow-hidden rounded-[8px] focus-within:shadow-[inset_0_0_0_2px_#2563EB]">
                          <button
                            type="button"
                            aria-expanded={isExpanded}
                            onClick={() => togglePolicy(policy.id)}
                            className="flex w-full flex-col gap-4 px-5 py-4 text-left transition-colors hover:bg-[#111827]/5 focus:outline-none sm:flex-row sm:items-center sm:justify-between"
                          >
                            <span className="flex min-w-0 items-start gap-3">
                              <InsurerLogo insurerName={basicInfo?.보험사} />
                              <span className="min-w-0 flex-1">
                                <span className="flex min-w-0 items-center gap-2">
                                  <span className="truncate text-base font-semibold text-[#111827]">
                                    {basicInfo?.상품명 ?? policy.fileName}
                                  </span>
                                  {basicInfo?.상품태그?.length ? (
                                    <span className="flex shrink-0 flex-wrap gap-1.5">
                                      {basicInfo.상품태그.map((tag) => (
                                        <TagBadge key={tag} tag={tag} />
                                      ))}
                                    </span>
                                  ) : null}
                                </span>
                                <span className="mt-1 block truncate text-sm text-[#111827]/70">
                                  {policy.fileName}
                                </span>
                              </span>
                            </span>
                            <span className="inline-flex shrink-0 items-center rounded-full border border-[#2563EB]/20 px-3 py-1 text-xs font-medium text-[#2563EB]">
                              {isExpanded ? "접기" : "자세히 보기"}
                            </span>
                          </button>

                          <div
                            className={`grid transition-[grid-template-rows] duration-200 ease-out ${
                              isExpanded ? "grid-rows-[1fr]" : "grid-rows-[0fr]"
                            }`}
                          >
                            <div className="overflow-hidden">
                              <PolicyDetail
                                policy={policy}
                                isExpanded={isExpanded}
                              />
                            </div>
                          </div>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </section>
            );
          })}
        </div>
      </section>

      {isUploadModalOpen ? (
        <UploadPolicyModal
          selectedName={analysis.selectedName}
          uploadPolicy={uploadPolicy}
          onClose={closeUploadModal}
          onAnalysisComplete={handleAdditionalAnalysisComplete}
        />
      ) : null}
    </main>
  );
}

function PolicyDetail({
  policy,
  isExpanded,
}: {
  policy: AnalyzedPolicy;
  isExpanded: boolean;
}) {
  const basicInfo = policy.result.기본정보;
  const detailItems = [
    ["보험사", basicInfo?.보험사],
    ["증권번호", basicInfo?.증권번호],
    ["계약자", basicInfo?.계약자],
    ["피보험자", basicInfo?.피보험자],
    ["보험기간", formatPeriod(basicInfo?.보험기간)],
    ["만기일", basicInfo?.만기일],
    ["납입기간", basicInfo?.납입기간],
    ["보험료", formatPremium(basicInfo?.보험료)],
  ].filter((item): item is [string, string] => Boolean(item[1]));

  return (
    <div
      className={`border-t border-[#111827]/10 bg-[#111827]/5 px-5 py-5 transition-all duration-200 ease-out ${
        isExpanded ? "translate-y-0 opacity-100" : "-translate-y-1 opacity-0"
      }`}
    >
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

      {basicInfo?.보험분류 !== "자동차" ? (
        <div className="mt-6">
          <h3 className="text-xs font-medium text-[#111827]/70">보장 내용</h3>
          <div className="mt-2 rounded-[8px] border border-[#111827]/10 bg-white px-5 py-4">
            <PolicyCoverageList coverages={policy.result.보장목록} />
          </div>
        </div>
      ) : null}
    </div>
  );
}

function InsurerLogo({ insurerName }: { insurerName?: string }) {
  const logo = findInsurerLogo(insurerName);

  return (
    <span className="flex h-10 min-w-[4.75rem] shrink-0 items-center justify-center rounded-[10px] border border-[#111827]/10 bg-white px-2.5">
      {logo ? (
        <span className="relative flex h-7 w-full items-center justify-center overflow-hidden">
          <Image
            src={logo.src}
            alt=""
            aria-hidden="true"
            fill
            sizes="76px"
            className={`object-contain ${logo.imageClassName ?? ""}`}
          />
        </span>
      ) : (
        <span className="text-xs font-semibold text-[#111827]/45">
          {(insurerName ?? "?").slice(0, 1)}
        </span>
      )}
    </span>
  );
}

function findInsurerLogo(insurerName?: string) {
  if (!insurerName) return undefined;

  const normalizedName = normalizeInsurerName(insurerName);
  return INSURER_LOGOS.find(({ aliases }) =>
    aliases.some((alias) =>
      normalizedName.includes(normalizeInsurerName(alias)),
    ),
  );
}

function normalizeInsurerName(value: string) {
  return value.replace(/\s+/g, "").replace(/주식회사|\(주\)|㈜/g, "");
}

function TagBadge({ tag }: { tag: string }) {
  return (
    <span
      className={`inline-flex h-6 items-center rounded-full border px-2 py-0 text-[11px] font-medium whitespace-nowrap ${TAG_STYLES[tag] ?? "border-[#111827]/10 bg-[#111827]/[0.04] text-[#111827]/60"}`}
    >
      {tag}
    </span>
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

function mergePolicyAnalysis(
  currentAnalysis: PolicyAnalysis,
  nextAnalysis: PolicyAnalysis,
): PolicyAnalysis {
  const selectedName =
    currentAnalysis.selectedName ?? nextAnalysis.selectedName;
  const policies = [...currentAnalysis.policies, ...nextAnalysis.policies];

  return {
    generatedAt: nextAnalysis.generatedAt,
    selectedName,
    policies: selectedName
      ? policies.filter(
          (policy) => getPolicyPersonName(policy) === selectedName,
        )
      : policies,
  };
}

function UploadPolicyModal({
  selectedName,
  uploadPolicy,
  onClose,
  onAnalysisComplete,
}: {
  selectedName?: string;
  uploadPolicy?: UploadPolicy;
  onClose: () => void;
  onAnalysisComplete: (analysis: PolicyAnalysis) => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-[#111827]/45 px-5 py-8"
      role="dialog"
      aria-modal="true"
      aria-labelledby="analysis-upload-modal-title"
    >
      <div className="w-full max-w-2xl rounded-[12px] bg-white p-5 shadow-[0_24px_80px_rgba(17,24,39,0.22)] sm:p-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2
              id="analysis-upload-modal-title"
              className="text-xl font-semibold tracking-normal text-[#111827]"
            >
              보험증권 더 올리기
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-[8px] px-3 py-2 text-sm font-medium text-[#111827]/60 transition-colors hover:bg-[#111827]/5 hover:text-[#111827] focus:ring-2 focus:ring-[#2563EB] focus:outline-none"
          >
            닫기
          </button>
        </div>

        <div className="mt-6">
          <UploadForm
            uploadPolicy={uploadPolicy}
            fixedSelectedName={selectedName}
            onAnalysisComplete={onAnalysisComplete}
            navigateToAnalysis={onClose}
            surface="modal"
          />
        </div>
      </div>
    </div>
  );
}
