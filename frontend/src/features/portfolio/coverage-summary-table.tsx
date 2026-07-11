import type { PortfolioSummary } from "./portfolio-api";

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
  "진단비",
  "수술비",
  "치료비",
  "입원",
  "통원",
  "후유장해",
  "사망",
  "간병",
  "기타",
];

export function CoverageSummaryTable({
  summary,
}: {
  summary: PortfolioSummary;
}) {
  const groups = buildCoverageGroups(summary);

  return (
    <div className="overflow-x-auto">
      <table
        aria-labelledby="coverage-total-title"
        className="w-full min-w-[42rem] text-left text-sm"
      >
        <thead className="bg-zinc-50 text-xs text-zinc-500">
          <tr>
            <th scope="col" className="px-6 py-3 font-medium">
              보장
            </th>
            <th scope="col" className="px-6 py-3 text-right font-medium">
              금액
            </th>
            <th scope="col" className="px-6 py-3 text-right font-medium">
              표시 기준
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
      <th scope="row" className="px-6 py-4 font-medium text-zinc-800">
        <details>
          <summary className="cursor-pointer marker:text-zinc-400">
            {row.displayName}
          </summary>
          <ul className="mt-3 space-y-1.5 text-xs font-normal text-zinc-500">
            {row.composition.map((source, index) => (
              <li key={`${source.policy_id ?? "policy"}-${index}`}>
                {coverageSourceLabel(source)} · {source.coverage_name} ·{" "}
                {source.original_amount}
              </li>
            ))}
          </ul>
        </details>
      </th>
      <td className="px-6 py-4 text-right font-semibold text-blue-600">
        {formatWon(row.totalAmount)}
      </td>
      <td className="px-6 py-4 text-right">
        <CoverageBasis tone="summed">
          {`합계 ${row.coverageCount}개`}
        </CoverageBasis>
      </td>
    </tr>
  );
}

function IndemnityCoverage({ row }: { row: IndemnityCoverageRow }) {
  return (
    <tr>
      <th scope="row" className="px-6 py-4 font-medium text-zinc-800">
        <p>{row.displayName}</p>
        <p className="mt-1 text-xs font-normal text-zinc-500">
          {coverageSourceLabel({
            insurer: row.insurer,
            product_name: row.productName,
          })}
          {row.crossInsurerDuplicate ? " · 중복 확인 필요" : ""}
        </p>
      </th>
      <td className="px-6 py-4 text-right font-medium text-zinc-700">
        {row.originalAmount || "금액 확인 필요"}
      </td>
      <td className="px-6 py-4 text-right">
        <CoverageBasis tone="indemnity">실손·비례형</CoverageBasis>
      </td>
    </tr>
  );
}

function IndividualCoverage({ row }: { row: IndividualCoverageRow }) {
  return (
    <tr>
      <th scope="row" className="px-6 py-4 font-medium text-zinc-800">
        <p>{row.displayName}</p>
        <p className="mt-1 text-xs font-normal text-zinc-500">
          {coverageSourceLabel({
            insurer: row.insurer,
            product_name: row.productName,
          })}
        </p>
        <p className="mt-1 text-xs font-normal text-zinc-400">{row.reason}</p>
      </th>
      <td className="px-6 py-4 text-right font-medium text-zinc-700">
        {row.originalAmount || "금액 확인 필요"}
      </td>
      <td className="px-6 py-4 text-right">
        <CoverageBasis tone="individual">개별 표시</CoverageBasis>
      </td>
    </tr>
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

function formatWon(amount: number) {
  return `${amount.toLocaleString("ko-KR")}원`;
}
