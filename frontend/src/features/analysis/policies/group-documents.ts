import type { AnalyzedInsurance } from "../types";

export function groupPolicyDocuments(documents: AnalyzedInsurance[]) {
  return documents.reduce<Record<string, AnalyzedInsurance[]>>(
    (groups, document) => {
      const classification = document.result.기본정보.보험분류;
      groups[classification] = [...(groups[classification] ?? []), document];
      return groups;
    },
    {},
  );
}
