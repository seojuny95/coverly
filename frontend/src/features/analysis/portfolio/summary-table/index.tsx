"use client";

import { CoverageTableRow } from "./rows";
import { buildCoverageGroups } from "./model";

import type { PortfolioSummary } from "../api";

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
