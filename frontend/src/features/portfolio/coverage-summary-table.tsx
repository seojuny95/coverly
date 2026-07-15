import type { ReactNode } from "react";

import type { PortfolioSummary } from "./portfolio-api";
import { formatKoreanWon } from "./money-format";

type SummedCoverageRow = {
  kind: "summed";
  key: string;
  displayName: string;
  totalAmount: number;
  coverageCount: number;
  composition: PortfolioSummary["totals"][number]["composition"];
};

type IndemnityCoverageRow = {
  kind: "indemnity";
  key: string;
  displayName: string;
  originalAmount?: string;
  insurer?: string;
  productName?: string;
  crossInsurerDuplicate: boolean;
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
  SummedCoverageRow | IndemnityCoverageRow | IndividualCoverageRow;

type CoverageGroup = {
  majorCategory: string;
  rows: CoverageRow[];
};

const MAJOR_CATEGORY_ORDER = [
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
  if (row.kind === "indemnity") return <IndemnityCoverage row={row} />;
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
                {coverageSourceLabel(source)} · {source.coverage_name} ·{" "}
                {source.original_amount}
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

function IndemnityCoverage({ row }: { row: IndemnityCoverageRow }) {
  return (
    <tr>
      <th scope="row" className="px-6 py-4 align-top font-medium text-zinc-800">
        <CoverageDisclosure
          label={row.displayName}
          badge={row.crossInsurerDuplicate ? <DuplicateBadge /> : null}
        >
          <p className="mt-3 text-xs font-normal break-words text-zinc-500">
            {coverageSourceLabel({
              insurer: row.insurer,
              product_name: row.productName,
            })}
          </p>
          {row.crossInsurerDuplicate ? (
            <p className="mt-1 text-xs font-normal text-amber-700">
              다른 보험사에도 같은 담보가 있어 중복 여부를 확인해보세요.
            </p>
          ) : null}
        </CoverageDisclosure>
      </th>
      <td className="px-6 py-4 text-right align-top font-medium text-zinc-700">
        {row.originalAmount || "금액 확인 필요"}
      </td>
      <td className="px-6 py-4 text-right align-top">
        <CoverageBasis tone="indemnity">실손보상</CoverageBasis>
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
  return (
    <details>
      <summary className="flex cursor-pointer list-none items-start gap-2 marker:content-none [&::-webkit-details-marker]:hidden">
        <span aria-hidden="true" className="mt-0.5 w-3 shrink-0 text-zinc-400">
          ›
        </span>
        <span className="inline-flex min-w-0 flex-wrap items-center gap-2 break-words">
          {label}
          {badge}
        </span>
      </summary>
      {children}
    </details>
  );
}

function DuplicateBadge() {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-semibold text-amber-700">
      중복 확인
    </span>
  );
}

function CoverageBasis({
  children,
  tone,
}: {
  children: string;
  tone: "summed" | "indemnity" | "individual";
}) {
  const toneClassName = {
    summed: "bg-blue-50 text-blue-700",
    indemnity: "bg-emerald-50 text-emerald-700",
    individual: "bg-zinc-100 text-zinc-600",
  }[tone];

  return (
    <span
      className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${toneClassName}`}
    >
      {children}
    </span>
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

  summary.indemnity_coverages.forEach((coverage, index) => {
    addRow(coverage.major_category, {
      kind: "indemnity",
      key: `indemnity-${coverage.policy_id ?? "policy"}-${coverage.coverage_name}-${index}`,
      displayName: coverage.coverage_name,
      originalAmount: coverage.original_amount,
      insurer: coverage.insurer,
      productName: coverage.product_name,
      crossInsurerDuplicate: coverage.cross_insurer_duplicate,
    });
  });

  summary.excluded_coverages.forEach((coverage, index) => {
    addRow(coverage.major_category, {
      kind: "individual",
      key: `individual-${coverage.policy_id ?? "policy"}-${coverage.coverage_name}-${index}`,
      displayName: coverage.coverage_name,
      originalAmount: coverage.original_amount,
      insurer: coverage.insurer,
      productName: coverage.product_name,
      reason: coverage.reason,
    });
  });

  return [...groups.entries()]
    .sort(
      ([leftCategory], [rightCategory]) =>
        categoryRank(leftCategory) - categoryRank(rightCategory),
    )
    .map(([majorCategory, rows]) => ({ majorCategory, rows }));
}

function categoryRank(category: string) {
  const index = MAJOR_CATEGORY_ORDER.indexOf(category);
  return index === -1 ? MAJOR_CATEGORY_ORDER.length : index;
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
  return coverageCount === 1
    ? "정액보상"
    : `정액보상 · ${coverageCount}개 합산`;
}
