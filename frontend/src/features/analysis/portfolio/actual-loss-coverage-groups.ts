import type { PortfolioSummary } from "./api";

export type ActualLossCoverage =
  PortfolioSummary["actual_loss_coverages"][number];

export type ActualLossCoverageGroup = {
  displayName: string;
  domain: string;
  normalizedName: string;
  majorCategory: string;
  duplicateAcrossContracts: boolean;
  originalAmount?: string;
  explanation: string;
  explanationBasis: ActualLossCoverage["explanation_basis"];
  items: ActualLossCoverage[];
};

export function groupActualLossCoverages(coverages: ActualLossCoverage[]) {
  const groups = new Map<string, ActualLossCoverageGroup>();

  for (const coverage of coverages) {
    const normalizedName = coverage.normalized_name || coverage.coverage_name;
    const domain = coverage.coverage_domain || "unknown";
    const key = `${domain}:${normalizedName}`;
    const group = groups.get(key);

    if (group) {
      group.items.push(coverage);
      group.duplicateAcrossContracts =
        group.duplicateAcrossContracts || coverage.duplicate_across_contracts;
      continue;
    }

    groups.set(key, {
      displayName: coverage.coverage_name,
      domain,
      normalizedName,
      majorCategory: coverage.major_category || "기타",
      duplicateAcrossContracts: coverage.duplicate_across_contracts,
      originalAmount: coverage.original_amount || undefined,
      explanation: coverage.explanation,
      explanationBasis: coverage.explanation_basis,
      items: [coverage],
    });
  }

  return [...groups.values()]
    .map((group) => ({
      ...group,
      originalAmount: groupedOriginalAmount(group.items),
    }))
    .sort((a, b) => a.displayName.localeCompare(b.displayName, "ko-KR"));
}

export function duplicateActualLossCoverageGroups(
  coverages: ActualLossCoverage[],
) {
  return groupActualLossCoverages(coverages).filter(
    (group) => group.duplicateAcrossContracts,
  );
}

function groupedOriginalAmount(coverages: ActualLossCoverage[]) {
  const amounts = new Set(
    coverages
      .map((coverage) => coverage.original_amount)
      .filter((amount): amount is string => Boolean(amount)),
  );
  if (amounts.size === 1) return [...amounts][0];
  if (amounts.size > 1) return "계약별 확인";
  return undefined;
}
