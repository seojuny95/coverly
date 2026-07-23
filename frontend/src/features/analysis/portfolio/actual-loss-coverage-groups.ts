import type { PortfolioSummary } from "./api";

export type ActualLossCoverage =
  PortfolioSummary["actual_loss_coverages"][number];

export type ActualLossCoverageGroup = {
  displayName: string;
  domain: string;
  normalizedName: string;
  items: ActualLossCoverage[];
};

export function duplicateActualLossCoverageGroups(
  coverages: ActualLossCoverage[],
) {
  const groups = new Map<string, ActualLossCoverageGroup>();

  for (const coverage of coverages) {
    if (!coverage.duplicate_across_contracts) continue;

    const normalizedName = coverage.normalized_name || coverage.coverage_name;
    const domain = coverage.coverage_domain || "unknown";
    const key = `${domain}:${normalizedName}`;
    const group = groups.get(key);

    if (group) {
      group.items.push(coverage);
      continue;
    }

    groups.set(key, {
      displayName: coverage.coverage_name,
      domain,
      normalizedName,
      items: [coverage],
    });
  }

  return [...groups.values()].sort((a, b) =>
    a.displayName.localeCompare(b.displayName, "ko-KR"),
  );
}

export function actualLossCoverageDescription(name: string) {
  const normalizedName = name.replace(/\s/g, "");

  if (normalizedName.includes("상해")) {
    return "상해로 병원 치료를 받았을 때 본인이 실제로 부담한 의료비를 약관 한도 안에서 보상하는 담보예요.";
  }
  if (normalizedName.includes("질병")) {
    return "질병으로 병원 치료를 받았을 때 본인이 실제로 부담한 의료비를 약관 한도 안에서 보상하는 담보예요.";
  }
  if (normalizedName.includes("입원")) {
    return "입원 치료 과정에서 실제로 부담한 의료비를 약관 한도 안에서 보상하는 담보예요.";
  }
  if (normalizedName.includes("통원") || normalizedName.includes("외래")) {
    return "통원·외래 진료 때 실제로 부담한 의료비를 약관 한도 안에서 보상하는 담보예요.";
  }
  if (normalizedName.includes("처방") || normalizedName.includes("약제")) {
    return "처방 조제비처럼 실제로 부담한 약제 관련 비용을 약관 한도 안에서 보상하는 담보예요.";
  }
  if (normalizedName.includes("벌금")) {
    return "정액 진단비가 아니라 실제 발생한 벌금 손해를 약관 한도 안에서 보상하는 실손형 담보예요.";
  }
  if (normalizedName.includes("배상")) {
    return "타인에게 배상해야 하는 실제 손해를 약관 한도 안에서 보상하는 실손형 담보예요.";
  }

  return "정해진 금액을 무조건 더해 받는 담보가 아니라, 실제 발생한 손해를 약관 한도 안에서 보상하는 실손형 담보예요.";
}
