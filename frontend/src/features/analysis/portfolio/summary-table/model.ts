import type { PortfolioSummary } from "../api";
import { groupActualLossCoverages } from "../actual-loss-coverage-groups";

export type SummedCoverageRow = {
  kind: "summed";
  key: string;
  displayName: string;
  totalAmount: number;
  coverageCount: number;
  composition: PortfolioSummary["totals"][number]["composition"];
};

export type ActualLossCoverageSource = {
  policyId?: string | null;
  coverageName: string;
  originalAmount?: string;
  insurer?: string;
  productName?: string;
};

export type ActualLossCoverageRow = {
  kind: "actual-loss";
  key: string;
  displayName: string;
  originalAmount?: string;
  duplicateAcrossContracts: boolean;
  sources: ActualLossCoverageSource[];
};

export type IndividualCoverageRow = {
  kind: "individual";
  key: string;
  displayName: string;
  originalAmount?: string;
  insurer?: string;
  productName?: string;
  reason: string;
};

export type CoverageRow =
  SummedCoverageRow | ActualLossCoverageRow | IndividualCoverageRow;

export type CoverageGroup = {
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

export function buildCoverageGroups(
  summary: PortfolioSummary,
): CoverageGroup[] {
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

  groupActualLossCoverages(
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
      sources: group.items.map((coverage) => ({
        policyId: coverage.policy_id,
        coverageName: coverage.coverage_name,
        originalAmount: coverage.original_amount,
        insurer: coverage.insurer ?? undefined,
        productName: coverage.product_name ?? undefined,
      })),
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

function compareCoverageGroups(a: CoverageGroup, b: CoverageGroup) {
  return (
    coverageGroupRank(a.majorCategory) - coverageGroupRank(b.majorCategory)
  );
}

function coverageGroupRank(majorCategory: string) {
  const index = COVERAGE_GROUP_ORDER.indexOf(majorCategory);
  return index === -1 ? COVERAGE_GROUP_ORDER.length : index;
}
