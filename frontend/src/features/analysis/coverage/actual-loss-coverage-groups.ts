import type { PortfolioSummary } from "./api";

export type ActualLossCoverage =
  PortfolioSummary["actual_loss_coverages"][number];

export type ActualLossCoverageGroup = {
  displayName: string;
  domain: string;
  normalizedName: string;
  majorCategory: string;
  duplicateAcrossContracts: boolean;
  contractCount: number;
  originalAmount?: string;
  explanation?: string;
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
      group.contractCount = countContracts(group.items);
      group.explanation = commonExplanation(group.items);
      continue;
    }

    groups.set(key, {
      displayName: coverage.coverage_name,
      domain,
      normalizedName,
      majorCategory: coverage.major_category || "기타",
      duplicateAcrossContracts: coverage.duplicate_across_contracts,
      contractCount: 1,
      originalAmount: coverage.original_amount || undefined,
      explanation: coverage.explanation,
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

function countContracts(coverages: ActualLossCoverage[]) {
  return new Set(
    coverages.map(
      (coverage) =>
        coverage.policy_id ??
        `${coverage.insurer}\u0000${coverage.product_name}`,
    ),
  ).size;
}

function commonExplanation(coverages: ActualLossCoverage[]) {
  const explanations = new Set(
    coverages.map(
      (coverage) => `${coverage.guidance_key}\u0000${coverage.explanation}`,
    ),
  );
  return explanations.size === 1 ? coverages[0]?.explanation : undefined;
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
