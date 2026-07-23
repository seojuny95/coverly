import type { PortfolioSummary } from "../api";

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
