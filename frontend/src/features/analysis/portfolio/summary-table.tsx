"use client";

import type { ReactNode } from "react";

import { CollapseRegion, useDisclosure } from "@/shared/components/disclosure";
import { Badge } from "@/shared/components/ui/badge";

import type { PortfolioSummary } from "./api";
import { formatKoreanWon } from "./money-format";

type SummedCoverageRow = {
  kind: "summed";
  key: string;
  displayName: string;
  totalAmount: number;
  coverageCount: number;
  composition: PortfolioSummary["totals"][number]["composition"];
};

type ActualLossCoverageRow = {
  kind: "actual-loss";
  key: string;
  displayName: string;
  originalAmount?: string;
  duplicateAcrossContracts: boolean;
  sources: ActualLossCoverageSource[];
};

type ActualLossCoverageSource = {
  policyId?: string | null;
  coverageName: string;
  originalAmount?: string;
  insurer?: string;
  productName?: string;
};

type IndividualCoverageRow = {
  kind: "individual";
  key: string;
  displayName: string;
  originalAmount?: string;
  insurer?: string;
  productName?: string;
  reason: string;
};

type CoverageRow =
  SummedCoverageRow | ActualLossCoverageRow | IndividualCoverageRow;

type CoverageGroup = {
  majorCategory: string;
  rows: CoverageRow[];
};

const COVERAGE_GROUP_ORDER = [
  "사망",
  "후유장해",
  "진단",
  "수술",
  "치료",
  "기타",
];

export function CoverageSummaryTable({
  summary,
}: {
  summary: PortfolioSummary;
}) {
  const groups = buildCoverageGroups(summary);
  const hasLifeThirdRows = groups.length > 0;

  return (
    <>
      {hasLifeThirdRows ? (
        <div className="overflow-x-auto">
          <table
            aria-labelledby="coverage-total-title"
            className="w-full min-w-[42rem] table-fixed text-left text-sm"
          >
            <colgroup>
              <col className="w-[52%]" />
              <col className="w-[23%]" />
              <col className="w-[25%]" />
            </colgroup>
            <thead className="bg-zinc-50 text-xs text-zinc-500">
              <tr>
                <th scope="col" className="px-6 py-3 font-medium">
                  보장
                </th>
                <th scope="col" className="px-6 py-3 text-right font-medium">
                  금액
                </th>
                <th scope="col" className="px-6 py-3 text-right font-medium">
                  금액 해석 기준
                </th>
              </tr>
            </thead>
            {groups.map((group) => (
              <tbody
                key={group.majorCategory}
                aria-label={group.majorCategory}
                className="divide-y divide-zinc-100 border-t border-zinc-200"
              >
                <tr className="bg-blue-50/50">
                  <th
                    colSpan={3}
                    scope="rowgroup"
                    className="px-6 py-3 text-xs font-semibold text-blue-700"
                  >
                    {group.majorCategory}
                  </th>
                </tr>
                {group.rows.map((row) => (
                  <CoverageTableRow key={row.key} row={row} />
                ))}
              </tbody>
            ))}
          </table>
        </div>
      ) : null}
    </>
  );
}

function CoverageTableRow({ row }: { row: CoverageRow }) {
  if (row.kind === "summed") return <SummedCoverage row={row} />;
  if (row.kind === "actual-loss") {
    return <ActualLossCoverage row={row} />;
  }
  return <IndividualCoverage row={row} />;
}

function SummedCoverage({ row }: { row: SummedCoverageRow }) {
  return (
    <tr>
      <th scope="row" className="px-6 py-4 align-top font-medium text-zinc-800">
        <CoverageDisclosure label={row.displayName}>
          <ul className="mt-3 space-y-1.5 text-xs font-normal break-words text-zinc-500">
            {row.composition.map((source, index) => (
              <li key={`${source.policy_id ?? "policy"}-${index}`}>
                {coverageSourceLabel({
                  insurer: source.insurer ?? undefined,
                  product_name: source.product_name ?? undefined,
                })}{" "}
                · {source.coverage_name} · {source.original_amount}
              </li>
            ))}
          </ul>
        </CoverageDisclosure>
      </th>
      <td className="px-6 py-4 text-right align-top font-semibold text-blue-600">
        {formatKoreanWon(row.totalAmount)}
      </td>
      <td className="px-6 py-4 text-right align-top">
        <CoverageBasis tone="summed">
          {summedBasisLabel(row.coverageCount)}
        </CoverageBasis>
      </td>
    </tr>
  );
}

function ActualLossCoverage({ row }: { row: ActualLossCoverageRow }) {
  return (
    <tr>
      <th scope="row" className="px-6 py-4 align-top font-medium text-zinc-800">
        <CoverageDisclosure
          label={row.displayName}
          badge={row.duplicateAcrossContracts ? <DuplicateBadge /> : null}
        >
          <ul className="mt-3 space-y-1.5 text-xs font-normal break-words text-zinc-500">
            {row.sources.map((source, index) => (
              <li
                key={`${source.policyId ?? "policy"}-${source.coverageName}-${index}`}
              >
                {coverageSourceLabel({
                  insurer: source.insurer,
                  product_name: source.productName,
                })}{" "}
                · {source.coverageName}
                {source.originalAmount ? ` · ${source.originalAmount}` : ""}
              </li>
            ))}
          </ul>
          {row.duplicateAcrossContracts ? (
            <p className="mt-1 text-xs font-normal text-amber-700">
              같은 실손형 담보가 여러 계약에서 확인됐어요.
            </p>
          ) : null}
        </CoverageDisclosure>
      </th>
      <td className="px-6 py-4 text-right align-top font-medium text-zinc-700">
        {row.originalAmount || "금액 확인 필요"}
      </td>
      <td className="px-6 py-4 text-right align-top">
        <CoverageBasis tone="actual-loss">실손 보장</CoverageBasis>
      </td>
    </tr>
  );
}

function IndividualCoverage({ row }: { row: IndividualCoverageRow }) {
  return (
    <tr>
      <th scope="row" className="px-6 py-4 align-top font-medium text-zinc-800">
        <CoverageDisclosure label={row.displayName}>
          <p className="mt-3 text-xs font-normal break-words text-zinc-500">
            {coverageSourceLabel({
              insurer: row.insurer,
              product_name: row.productName,
            })}
          </p>
          <p className="mt-1 text-xs font-normal break-words text-zinc-400">
            {row.reason}
          </p>
        </CoverageDisclosure>
      </th>
      <td className="px-6 py-4 text-right align-top font-medium text-zinc-700">
        {row.originalAmount || "금액 확인 필요"}
      </td>
      <td className="px-6 py-4 text-right align-top">
        <CoverageBasis tone="individual">개별 확인</CoverageBasis>
      </td>
    </tr>
  );
}

function CoverageDisclosure({
  children,
  label,
  badge = null,
}: {
  children: ReactNode;
  label: string;
  badge?: ReactNode;
}) {
  const { expanded, toggle, panelId } = useDisclosure();

  return (
    <div>
      <button
        type="button"
        aria-expanded={expanded}
        aria-controls={panelId}
        onClick={toggle}
        className="group flex w-full cursor-pointer items-start gap-2 text-left focus-visible:rounded focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-blue-600"
      >
        <span
          aria-hidden="true"
          className={`mt-0.5 w-3 shrink-0 text-zinc-400 transition-transform duration-200 ease-out motion-reduce:transition-none ${
            expanded ? "rotate-90" : ""
          }`}
        >
          ›
        </span>
        <span className="inline-flex min-w-0 flex-wrap items-center gap-2 break-words">
          {label}
          {badge}
        </span>
      </button>
      <CollapseRegion expanded={expanded} id={panelId}>
        <div
          className={`transition-[opacity,transform] duration-200 ease-out motion-reduce:transition-none ${
            expanded
              ? "translate-y-0 opacity-100 delay-75"
              : "-translate-y-1 opacity-0"
          }`}
        >
          {children}
        </div>
      </CollapseRegion>
    </div>
  );
}

function DuplicateBadge() {
  return (
    <Badge
      variant="warning"
      className="h-auto px-2 py-0.5 text-[11px] font-semibold"
    >
      중복 확인
    </Badge>
  );
}

function CoverageBasis({
  children,
  tone,
}: {
  children: string;
  tone: "summed" | "actual-loss" | "individual";
}) {
  const badgeVariant = {
    summed: "info",
    "actual-loss": "success",
    individual: "neutral",
  } as const;

  return (
    <Badge
      variant={badgeVariant[tone]}
      className="h-auto px-2.5 py-1 text-xs font-semibold"
    >
      {children}
    </Badge>
  );
}

function buildCoverageGroups(summary: PortfolioSummary): CoverageGroup[] {
  const groups = new Map<string, CoverageRow[]>();
  const addRow = (majorCategory: string | undefined, row: CoverageRow) => {
    const category = majorCategory || "기타";
    const rows = groups.get(category) ?? [];
    rows.push(row);
    groups.set(category, rows);
  };

  summary.totals.forEach((total, index) => {
    addRow(total.majorCategory, {
      kind: "summed",
      key: `summed-${total.normalizedName}-${index}`,
      displayName: total.category,
      totalAmount: total.totalAmount,
      coverageCount: total.coverageCount,
      composition: total.composition,
    });
  });

  groupedActualLossCoverages(
    summary.actual_loss_coverages.filter(
      (coverage) => !coverage.is_damage_policy,
    ),
  ).forEach((group) => {
    addRow(group.majorCategory, {
      kind: "actual-loss",
      key: `actual-loss-${group.domain}-${group.normalizedName}`,
      displayName: group.displayName,
      originalAmount: group.originalAmount,
      duplicateAcrossContracts: group.duplicateAcrossContracts,
      sources: group.sources,
    });
  });

  summary.excluded_coverages.forEach((coverage, index) => {
    addRow(coverage.major_category, {
      kind: "individual",
      key: `individual-${coverage.policy_id ?? "policy"}-${coverage.coverage_name}-${index}`,
      displayName: coverage.coverage_name,
      originalAmount: coverage.original_amount,
      insurer: coverage.insurer ?? undefined,
      productName: coverage.product_name ?? undefined,
      reason: coverage.reason,
    });
  });

  return [...groups.entries()]
    .map(([majorCategory, rows]) => ({
      majorCategory,
      rows,
    }))
    .sort(compareCoverageGroups);
}

function groupedActualLossCoverages(
  coverages: PortfolioSummary["actual_loss_coverages"],
) {
  const groups = new Map<
    string,
    {
      displayName: string;
      domain: string;
      normalizedName: string;
      majorCategory: string | undefined;
      duplicateAcrossContracts: boolean;
      originalAmounts: Set<string>;
      sources: ActualLossCoverageSource[];
    }
  >();

  for (const coverage of coverages) {
    const normalizedName = coverage.normalized_name || coverage.coverage_name;
    const domain = coverage.coverage_domain || "unknown";
    const key = `${domain}:${normalizedName}`;
    const group = groups.get(key);
    const source: ActualLossCoverageSource = {
      policyId: coverage.policy_id,
      coverageName: coverage.coverage_name,
      originalAmount: coverage.original_amount,
      insurer: coverage.insurer ?? undefined,
      productName: coverage.product_name ?? undefined,
    };

    if (group) {
      group.duplicateAcrossContracts =
        group.duplicateAcrossContracts || coverage.duplicate_across_contracts;
      group.sources.push(source);
      if (coverage.original_amount) {
        group.originalAmounts.add(coverage.original_amount);
      }
      continue;
    }

    groups.set(key, {
      displayName: coverage.coverage_name,
      domain,
      normalizedName,
      majorCategory: coverage.major_category,
      duplicateAcrossContracts: coverage.duplicate_across_contracts,
      originalAmounts: new Set(
        coverage.original_amount ? [coverage.original_amount] : [],
      ),
      sources: [source],
    });
  }

  return [...groups.values()].map((group) => ({
    ...group,
    duplicateAcrossContracts:
      group.duplicateAcrossContracts || group.sources.length > 1,
    originalAmount:
      group.originalAmounts.size === 1
        ? [...group.originalAmounts][0]
        : group.originalAmounts.size > 1
          ? "계약별 확인"
          : undefined,
  }));
}

function compareCoverageGroups(a: CoverageGroup, b: CoverageGroup) {
  return (
    coverageGroupRank(a.majorCategory) - coverageGroupRank(b.majorCategory)
  );
}

function coverageGroupRank(majorCategory: string) {
  const index = COVERAGE_GROUP_ORDER.indexOf(majorCategory);
  return index === -1 ? COVERAGE_GROUP_ORDER.length : index;
}

function coverageSourceLabel(source: {
  insurer?: string;
  product_name?: string;
}) {
  return [source.insurer ?? "보험사 확인 필요", source.product_name]
    .filter(Boolean)
    .join(" · ");
}

function summedBasisLabel(coverageCount: number) {
  return coverageCount === 1 ? "합산" : `${coverageCount}개 합산`;
}
