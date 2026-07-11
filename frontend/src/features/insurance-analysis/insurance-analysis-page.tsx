"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import {
  CoverlyLogo,
  PixelEyebrow,
  ghostButtonClassName,
  primaryButtonClassName,
} from "../../components/coverly-brand";

import insurerLogos from "./insurer-logos.json";
import {
  type AnalyzedInsurance,
  type InsuranceAnalysis,
  getInsuredPersonName,
  loadInsuranceAnalysis,
  saveInsuranceAnalysis,
} from "./insurance-analysis-store";
import type {
  InsuranceBasicInfo,
  InsurancePremium,
  InsurancePeriod,
} from "../insurance-upload/upload-insurance";
import {
  InsuranceUploadForm,
  type UploadInsurance,
} from "../insurance-upload/insurance-upload-form";
import { InsuranceCoverageList } from "./insurance-coverage-list";
import { CoverageTotalTable } from "../portfolio/coverage-total-table";
import { InsuranceChatbot } from "../portfolio/insurance-chatbot";
import { PortfolioAnalysisPanel } from "../portfolio/portfolio-analysis-panel";
import { usePortfolioSummary } from "../portfolio/use-portfolio-summary";

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

type InsuranceAnalysisPageProps = {
  uploadInsurance?: UploadInsurance;
};

export function InsuranceAnalysisPage({
  uploadInsurance,
}: InsuranceAnalysisPageProps = {}) {
  const [analysis, setAnalysis] = useState<InsuranceAnalysis | null>();
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<"insurance" | "analysis">(
    "insurance",
  );
  const [expandedInsuranceIds, setExpandedInsuranceIds] = useState<Set<string>>(
    () => new Set(),
  );

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      setAnalysis(loadInsuranceAnalysis());
    }, 0);

    return () => window.clearTimeout(timeoutId);
  }, []);

  const insuranceDocuments = useMemo(
    () => analysis?.insuranceDocuments ?? [],
    [analysis],
  );
  const groupedInsuranceDocuments = useMemo(
    () => groupInsuranceDocuments(insuranceDocuments),
    [insuranceDocuments],
  );
  const counts = useMemo(
    () => countInsuranceDocuments(insuranceDocuments),
    [insuranceDocuments],
  );
  const portfolioSummary = usePortfolioSummary(insuranceDocuments);

  const toggleInsurance = (policyId: string) => {
    setExpandedInsuranceIds((current) => {
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

  const handleAdditionalAnalysisComplete = (
    nextAnalysis: InsuranceAnalysis,
  ) => {
    if (!analysis) return;

    const mergedAnalysis = mergeInsuranceAnalysis(analysis, nextAnalysis);
    saveInsuranceAnalysis(mergedAnalysis);
    setAnalysis(mergedAnalysis);
  };

  if (analysis === undefined) {
    return (
      <main className="relative flex min-h-screen items-center justify-center bg-white px-5 text-zinc-950">
        <CoverlyLogo className="absolute top-6 left-6" />
        <div className="flex flex-col items-center gap-4">
          <span className="size-2 animate-pulse bg-blue-600" />
          <p className="text-sm font-medium text-zinc-500">
            분석 결과를 불러오고 있어요.
          </p>
        </div>
      </main>
    );
  }

  if (!analysis || insuranceDocuments.length === 0) {
    return (
      <main className="relative flex min-h-screen items-center justify-center bg-white px-5 text-zinc-950">
        <CoverlyLogo className="absolute top-6 left-6" />
        <section className="w-full max-w-lg rounded-2xl border border-zinc-200 bg-white px-6 py-8 text-center shadow-[10px_10px_0_#e8edff]">
          <div className="mb-5 flex justify-center">
            <PixelEyebrow>분석 결과</PixelEyebrow>
          </div>
          <h1 className="text-2xl font-semibold tracking-[-0.04em]">
            분석할 보험증권이 없어요
          </h1>
          <p className="mt-3 text-sm leading-6 text-zinc-500">
            보험증권 PDF를 올리면 정리한 결과를 여기에서 볼 수 있어요.
          </p>
          <Link href="/upload" className={`mt-6 ${primaryButtonClassName}`}>
            보험증권 올리기
          </Link>
        </section>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-white px-5 py-6 text-zinc-950 sm:px-6">
      <header className="mx-auto flex w-full max-w-6xl items-center gap-4">
        <CoverlyLogo />
      </header>

      <section className="mx-auto mt-10 w-full max-w-6xl">
        <nav
          aria-label="보험 정보 보기"
          className="mb-8 flex gap-1 border-b border-zinc-200"
        >
          <TabButton
            active={activeTab === "insurance"}
            onClick={() => setActiveTab("insurance")}
          >
            내 보험
          </TabButton>
          <TabButton
            active={activeTab === "analysis"}
            onClick={() => setActiveTab("analysis")}
          >
            보험 분석
          </TabButton>
        </nav>
        {activeTab === "insurance" ? (
          <>
            <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <div className="mb-4">
                  <PixelEyebrow>나의 보장 지도</PixelEyebrow>
                </div>
                <h1 className="text-3xl font-semibold tracking-[-0.05em] text-zinc-950 sm:text-4xl">
                  내 보험을 종류별로 정리했어요
                </h1>
                <p className="mt-3 text-sm leading-6 text-zinc-500">
                  {analysis.selectedName
                    ? `${analysis.selectedName}님의 보험 ${insuranceDocuments.length}개를 종류별로 보기 쉽게 정리했어요.`
                    : `보험 ${insuranceDocuments.length}개를 종류별로 보기 쉽게 정리했어요.`}
                </p>
              </div>
              <div className="flex flex-col items-start gap-3 sm:items-end">
                <button
                  type="button"
                  onClick={openUploadModal}
                  className={primaryButtonClassName}
                >
                  보험증권 더 올리기
                </button>
                <p className="font-mono text-[10px] tracking-[0.04em] text-zinc-400">
                  정리한 시각 {formatDateTime(analysis.generatedAt)}
                </p>
              </div>
            </div>

            <dl className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
              {CLASSIFICATION_ORDER.map((classification) => (
                <div
                  key={classification}
                  className="rounded-xl border border-zinc-200 bg-white px-4 py-4 shadow-[4px_4px_0_#f4f4f5]"
                >
                  <dt className="text-xs font-medium text-zinc-500">
                    {classification}
                  </dt>
                  <dd className="mt-3 text-3xl font-semibold tracking-[-0.05em] text-blue-600">
                    {counts[classification] ?? 0}
                  </dd>
                </div>
              ))}
            </dl>

            <CoverageTotalTable
              status={portfolioSummary.state.status}
              summary={
                portfolioSummary.state.status === "success"
                  ? portfolioSummary.state.summary
                  : undefined
              }
              onRetry={portfolioSummary.retry}
            />

            <div className="mt-8 space-y-5">
              {CLASSIFICATION_ORDER.map((classification) => {
                const classificationInsuranceDocuments =
                  groupedInsuranceDocuments[classification] ?? [];
                if (classificationInsuranceDocuments.length === 0) return null;

                return (
                  <section
                    key={classification}
                    className="overflow-hidden rounded-2xl border border-zinc-200 bg-white"
                  >
                    <div className="border-b border-zinc-100 bg-zinc-50/60 px-5 py-4">
                      <h2 className="text-lg font-semibold tracking-[-0.03em]">
                        {classification}
                      </h2>
                      <p className="mt-1 text-sm text-zinc-500">
                        보험 {classificationInsuranceDocuments.length}개
                      </p>
                    </div>

                    <ul className="divide-y divide-zinc-100">
                      {classificationInsuranceDocuments.map(
                        (insuranceDocument) => {
                          const isExpanded = expandedInsuranceIds.has(
                            insuranceDocument.id,
                          );
                          const basicInfo = insuranceDocument.result.기본정보;

                          return (
                            <li key={insuranceDocument.id}>
                              <button
                                type="button"
                                aria-expanded={isExpanded}
                                onClick={() =>
                                  toggleInsurance(insuranceDocument.id)
                                }
                                className="flex w-full flex-col gap-4 px-5 py-4 text-left transition-colors hover:bg-zinc-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-inset sm:flex-row sm:items-center sm:justify-between"
                              >
                                <span className="flex min-w-0 items-start gap-3">
                                  <InsurerLogo
                                    insurerName={basicInfo?.보험사}
                                  />
                                  <span className="min-w-0 flex-1">
                                    <span className="flex min-w-0 items-center gap-2">
                                      <span className="truncate text-base font-semibold text-zinc-950">
                                        {basicInfo?.상품명 ??
                                          insuranceDocument.fileName}
                                      </span>
                                      {basicInfo?.상품태그?.length ? (
                                        <span className="flex shrink-0 flex-wrap gap-1.5">
                                          {basicInfo.상품태그.map((tag) => (
                                            <TagBadge key={tag} tag={tag} />
                                          ))}
                                        </span>
                                      ) : null}
                                    </span>
                                    <span className="mt-1 block truncate text-sm text-zinc-500">
                                      {insuranceDocument.fileName}
                                    </span>
                                  </span>
                                </span>
                                <span className="inline-flex shrink-0 items-center rounded-lg border border-blue-100 bg-blue-50 px-3 py-1 text-xs font-medium text-blue-700">
                                  {isExpanded ? "접기" : "자세히 보기"}
                                </span>
                              </button>

                              <div
                                className={`grid transition-[grid-template-rows] duration-200 ease-out ${
                                  isExpanded
                                    ? "grid-rows-[1fr]"
                                    : "grid-rows-[0fr]"
                                }`}
                              >
                                <div className="overflow-hidden">
                                  <InsuranceDetail
                                    insuranceDocument={insuranceDocument}
                                    isExpanded={isExpanded}
                                  />
                                </div>
                              </div>
                            </li>
                          );
                        },
                      )}
                    </ul>
                  </section>
                );
              })}
            </div>
          </>
        ) : (
          <div>
            <div className="mb-7">
              <PixelEyebrow>내 보험 분석</PixelEyebrow>
              <h1 className="mt-4 text-3xl font-semibold tracking-[-0.05em] sm:text-4xl">
                내 보험을 당신 편에서 살펴봐요
              </h1>
              <p className="mt-3 text-sm leading-6 text-zinc-500">
                확인한 강점과 보장 공백, 이어서 생각해볼 질문을 근거와 함께
                정리해요.
              </p>
            </div>
            <PortfolioAnalysisPanel
              active={activeTab === "analysis"}
              documents={insuranceDocuments}
            />
          </div>
        )}
      </section>

      <InsuranceChatbot documents={insuranceDocuments} />

      {isUploadModalOpen ? (
        <UploadInsuranceModal
          selectedName={analysis.selectedName}
          uploadInsurance={uploadInsurance}
          onClose={closeUploadModal}
          onAnalysisComplete={handleAdditionalAnalysisComplete}
        />
      ) : null}
    </main>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={`border-b-2 px-5 py-3 text-sm font-semibold transition-colors ${active ? "border-blue-600 text-blue-600" : "border-transparent text-zinc-500 hover:text-zinc-900"}`}
    >
      {children}
    </button>
  );
}

function InsuranceDetail({
  insuranceDocument,
  isExpanded,
}: {
  insuranceDocument: AnalyzedInsurance;
  isExpanded: boolean;
}) {
  const basicInfo = insuranceDocument.result.기본정보;
  const detailItems = [
    ["보험사", basicInfo?.보험사],
    ["증권번호", basicInfo?.증권번호],
    ["계약자", basicInfo?.계약자],
    ["피보험자", basicInfo?.피보험자],
    ["보험기간", formatPeriod(basicInfo?.보험기간)],
    ["만기일", basicInfo?.만기일],
    ["납입기간", basicInfo?.납입기간],
    ["보험료", formatPremium(basicInfo?.보험료)],
    ["차량명", basicInfo?.차량정보?.차량명],
    ["차량번호", basicInfo?.차량정보?.차량번호],
    ["연식", basicInfo?.차량정보?.연식],
  ].filter((item): item is [string, string] => Boolean(item[1]));

  return (
    <div
      className={`border-t border-zinc-100 bg-zinc-50/70 px-5 py-5 transition-all duration-200 ease-out ${
        isExpanded ? "translate-y-0 opacity-100" : "-translate-y-1 opacity-0"
      }`}
    >
      <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {detailItems.map(([label, value]) => (
          <div key={label}>
            <dt className="text-xs font-medium text-zinc-500">{label}</dt>
            <dd className="mt-1 text-sm font-medium break-words text-zinc-800">
              {value}
            </dd>
          </div>
        ))}
      </dl>

      <div className="mt-6">
        <h3 className="text-xs font-medium text-zinc-500">보장 내용</h3>
        <div className="mt-2 rounded-xl border border-zinc-200 bg-white px-5 py-4">
          <InsuranceCoverageList
            coverages={insuranceDocument.result.보장목록}
            status={insuranceDocument.result.분석상태}
          />
        </div>
      </div>
    </div>
  );
}

function InsurerLogo({ insurerName }: { insurerName?: string }) {
  const logo = findInsurerLogo(insurerName);

  return (
    <span className="flex h-10 min-w-[4.75rem] shrink-0 items-center justify-center rounded-xl border border-zinc-200 bg-white px-2.5">
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
        <span className="text-xs font-semibold text-zinc-400">
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

function groupInsuranceDocuments(insuranceDocuments: AnalyzedInsurance[]) {
  return insuranceDocuments.reduce<Record<string, AnalyzedInsurance[]>>(
    (groups, insuranceDocument) => {
      const classification =
        insuranceDocument.result.기본정보?.보험분류 ?? "미분류";
      groups[classification] = [
        ...(groups[classification] ?? []),
        insuranceDocument,
      ];
      return groups;
    },
    {},
  );
}

function countInsuranceDocuments(insuranceDocuments: AnalyzedInsurance[]) {
  return insuranceDocuments.reduce<Record<string, number>>(
    (counts, insuranceDocument) => {
      const classification =
        insuranceDocument.result.기본정보?.보험분류 ?? "미분류";
      counts[classification] = (counts[classification] ?? 0) + 1;
      return counts;
    },
    {},
  );
}

function formatPeriod(
  period: InsurancePeriod | InsuranceBasicInfo["보험기간"],
) {
  if (!period?.시작일 || !period.종료일) return undefined;
  return `${period.시작일} - ${period.종료일}`;
}

function formatPremium(
  premium: InsurancePremium | InsuranceBasicInfo["보험료"],
) {
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

function mergeInsuranceAnalysis(
  currentAnalysis: InsuranceAnalysis,
  nextAnalysis: InsuranceAnalysis,
): InsuranceAnalysis {
  const selectedName =
    currentAnalysis.selectedName ?? nextAnalysis.selectedName;
  const insuranceDocuments = [
    ...currentAnalysis.insuranceDocuments,
    ...nextAnalysis.insuranceDocuments,
  ];

  return {
    generatedAt: nextAnalysis.generatedAt,
    selectedName,
    insuranceDocuments: selectedName
      ? insuranceDocuments.filter(
          (insuranceDocument) =>
            getInsuredPersonName(insuranceDocument) === selectedName,
        )
      : insuranceDocuments,
  };
}

function UploadInsuranceModal({
  selectedName,
  uploadInsurance,
  onClose,
  onAnalysisComplete,
}: {
  selectedName?: string;
  uploadInsurance?: UploadInsurance;
  onClose: () => void;
  onAnalysisComplete: (analysis: InsuranceAnalysis) => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-950/45 px-5 py-8 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="analysis-upload-modal-title"
    >
      <div className="w-full max-w-2xl rounded-2xl border border-zinc-200 bg-white p-5 shadow-[12px_12px_0_rgba(232,237,255,0.45)] sm:p-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2
              id="analysis-upload-modal-title"
              className="text-xl font-semibold tracking-[-0.04em] text-zinc-950"
            >
              보험증권 더 올리기
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className={ghostButtonClassName}
          >
            닫기
          </button>
        </div>

        <div className="mt-6">
          <InsuranceUploadForm
            uploadInsurance={uploadInsurance}
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
