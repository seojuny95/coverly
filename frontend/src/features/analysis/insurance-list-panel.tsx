import { SectionLabel } from "../../shared/components/section-label";
import { Button } from "@/shared/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/shared/components/ui/tooltip";
import { POLICY_CLASSIFICATIONS } from "../../shared/api/generated-runtime";
import { CircleHelp } from "lucide-react";

import { InsurerLogo, InsuranceDetail, TagBadge } from "./policy-detail";
import type { AnalyzedInsurance } from "./store";
import { CoverageTotalTable } from "./portfolio/total-table";
import type { PortfolioSummary } from "./portfolio/api";

type InsuranceListPanelProps = {
  selectedName?: string | null;
  generatedAt: string;
  groupedInsuranceDocuments: Record<string, AnalyzedInsurance[]>;
  coverageTotalStatus: "loading" | "error" | "success";
  coverageTotalSummary?: PortfolioSummary;
  onRetryCoverageTotal: () => void;
  isExpanded: (id: string) => boolean;
  onToggle: (id: string) => void;
  onOpenUploadModal: () => void;
};

export function InsuranceListPanel({
  selectedName,
  generatedAt,
  groupedInsuranceDocuments,
  coverageTotalStatus,
  coverageTotalSummary,
  onRetryCoverageTotal,
  isExpanded,
  onToggle,
  onOpenUploadModal,
}: InsuranceListPanelProps) {
  const classificationTypeCount = POLICY_CLASSIFICATIONS.length;

  return (
    <div
      id="insurance-tabpanel"
      role="tabpanel"
      aria-labelledby="insurance-tab"
      tabIndex={0}
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="mb-4">
            <SectionLabel>나의 보장 지도</SectionLabel>
          </div>
          <h1 className="text-3xl font-semibold tracking-[-0.05em] text-zinc-950 sm:text-4xl">
            내 보험을 종류별로 정리했어요
          </h1>
          <p className="mt-3 text-sm leading-6 text-zinc-500">
            {selectedName
              ? `${selectedName}님의 보험을 ${classificationTypeCount}가지 종류로 보기 쉽게 정리했어요.`
              : `보험을 ${classificationTypeCount}가지 종류로 보기 쉽게 정리했어요.`}
          </p>
        </div>
        <div className="flex flex-col items-start gap-3 sm:items-end">
          <Button type="button" onClick={onOpenUploadModal}>
            보험증권 더 올리기
          </Button>
          <p className="font-mono text-[10px] tracking-[0.04em] text-zinc-400">
            정리한 시각 {formatDateTime(generatedAt)}
          </p>
        </div>
      </div>

      <dl className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {POLICY_CLASSIFICATIONS.map((classification) => (
          <div
            key={classification}
            className="relative rounded-xl border border-zinc-200 bg-white px-4 py-4 shadow-[4px_4px_0_#f4f4f5]"
          >
            <dt className="flex items-start justify-between gap-2 text-xs font-medium text-zinc-500">
              <span>{classification}</span>
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    aria-label={`${classification} 설명`}
                    className="inline-flex size-6 items-center justify-center rounded-full text-zinc-400 transition-colors hover:bg-zinc-100 hover:text-zinc-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-600"
                  >
                    <CircleHelp aria-hidden="true" className="size-4" />
                  </button>
                </TooltipTrigger>
                <TooltipContent
                  side="top"
                  align="end"
                  sideOffset={4}
                  className="max-w-64 px-3 py-2 text-left text-xs leading-5 font-normal"
                >
                  {POLICY_CLASSIFICATION_DESCRIPTIONS[classification]}
                </TooltipContent>
              </Tooltip>
            </dt>
            <dd className="mt-3 text-3xl font-semibold tracking-[-0.05em] text-blue-600">
              {groupedInsuranceDocuments[classification]?.length ?? 0}
            </dd>
          </div>
        ))}
      </dl>

      <CoverageTotalTable
        status={coverageTotalStatus}
        summary={coverageTotalSummary}
        onRetry={onRetryCoverageTotal}
      />

      <div className="mt-8 space-y-5">
        {POLICY_CLASSIFICATIONS.map((classification) => {
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
                <p className="mt-1 text-sm leading-6 text-zinc-500">
                  {POLICY_CLASSIFICATION_DESCRIPTIONS[classification]}
                </p>
                <p className="mt-1 text-xs font-medium text-zinc-400">
                  보험 {classificationInsuranceDocuments.length}개
                </p>
              </div>

              <ul className="divide-y divide-zinc-100">
                {classificationInsuranceDocuments.map((insuranceDocument) => {
                  const expanded = isExpanded(insuranceDocument.id);
                  const basicInfo = insuranceDocument.result.기본정보;

                  return (
                    <li key={insuranceDocument.id}>
                      <button
                        type="button"
                        aria-expanded={expanded}
                        onClick={() => onToggle(insuranceDocument.id)}
                        className="flex w-full flex-col gap-4 px-5 py-4 text-left transition-colors hover:bg-zinc-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-inset sm:flex-row sm:items-center sm:justify-between"
                      >
                        <span className="flex min-w-0 items-start gap-3">
                          <InsurerLogo
                            insurerName={basicInfo?.보험사 ?? undefined}
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
                          {expanded ? "접기" : "자세히 보기"}
                        </span>
                      </button>

                      <div
                        className={`grid transition-[grid-template-rows] duration-200 ease-out ${
                          expanded ? "grid-rows-[1fr]" : "grid-rows-[0fr]"
                        }`}
                      >
                        <div className="overflow-hidden">
                          <InsuranceDetail
                            insuranceDocument={insuranceDocument}
                            isExpanded={expanded}
                          />
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
    </div>
  );
}

const POLICY_CLASSIFICATION_DESCRIPTIONS = {
  생명보험:
    "사망, 생존, 노후처럼 사람의 생명과 기간을 중심으로 보장을 살펴보는 보험이에요.",
  제3보험:
    "질병, 상해, 간병, 실손의료비처럼 사람의 건강 상태와 치료 부담을 살펴보는 보험이에요.",
  손해보험:
    "자동차, 화재, 배상책임처럼 사고로 생긴 재산 손해나 법적 책임을 살펴보는 보험이에요.",
  미분류: "현재 올린 증권만으로 보험 종류를 뚜렷하게 나누기 어려운 항목이에요.",
} as const;

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}
