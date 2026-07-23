import { describe, expect, it } from "vitest";

import {
  type ActualLossCoverage,
  duplicateActualLossCoverageGroups,
  groupActualLossCoverages,
} from "./actual-loss-coverage-groups";

function actualLossCoverage(
  overrides: Partial<ActualLossCoverage> = {},
): ActualLossCoverage {
  return {
    policy_id: "policy-1",
    insurer: "보험사A",
    product_name: "상품A",
    coverage_name: "상해실손의료비",
    normalized_name: "상해실손의료비",
    coverage_domain: "medical_expense",
    is_medical_indemnity: true,
    is_damage_policy: false,
    duplicate_across_contracts: false,
    guidance_key: "injury_medical_expense",
    explanation: "서버에서 분류한 상해 실손 안내예요.",
    explanation_basis: "generated_guidance",
    original_amount: "5,000만원",
    major_category: "치료",
    ...overrides,
  };
}

describe("actual-loss coverage groups", () => {
  it("groups the same backend identity and keeps its grounded explanation", () => {
    const groups = groupActualLossCoverages([
      actualLossCoverage({ duplicate_across_contracts: true }),
      actualLossCoverage({
        policy_id: "policy-2",
        insurer: "보험사B",
        duplicate_across_contracts: true,
      }),
    ]);

    expect(groups).toHaveLength(1);
    expect(groups[0]).toMatchObject({
      duplicateAcrossContracts: true,
      explanation: "서버에서 분류한 상해 실손 안내예요.",
      explanationBasis: "generated_guidance",
    });
    expect(groups[0].items).toHaveLength(2);
  });

  it("does not infer a contract duplicate from repeated rows alone", () => {
    const duplicates = duplicateActualLossCoverageGroups([
      actualLossCoverage(),
      actualLossCoverage({ coverage_name: "상해 실손의료비" }),
    ]);

    expect(duplicates).toEqual([]);
  });

  it("keeps the same normalized name separate across coverage domains", () => {
    const groups = groupActualLossCoverages([
      actualLossCoverage(),
      actualLossCoverage({
        coverage_domain: "travel_medical_expense",
        is_medical_indemnity: false,
        guidance_key: "travel_medical_expense",
        explanation: "여행 중 의료비에 대한 일반 안내예요.",
      }),
    ]);

    expect(groups).toHaveLength(2);
  });
});
