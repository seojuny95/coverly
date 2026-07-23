import {
  type AnalyzedInsurance,
  getInsuredPersonName,
} from "../../analysis/store";

export function getInsuranceNameOptions(
  insuranceDocuments: AnalyzedInsurance[],
) {
  const counts = new Map<string, number>();
  for (const insuranceDocument of insuranceDocuments) {
    const personName = getInsuredPersonName(insuranceDocument);
    if (!personName) continue;
    counts.set(personName, (counts.get(personName) ?? 0) + 1);
  }

  return Array.from(counts.entries()).map(([name, count]) => ({
    name,
    count,
  }));
}
