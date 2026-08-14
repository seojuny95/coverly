import type { ReactNode } from "react";

import { CollapseRegion, useDisclosure } from "@/shared/components/disclosure";
import { Badge } from "@/shared/components/ui/badge";

import { formatKoreanWon } from "../money-format";
import type {
  ActualLossCoverageRow,
  CoverageRow,
  IndividualCoverageRow,
  SummedCoverageRow,
} from "./model";

export function CoverageTableRow({ row }: { row: CoverageRow }) {
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
