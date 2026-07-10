import { afterEach, expect, test } from "vitest";

import { loadInsuranceAnalysis } from "./insurance-analysis-store";

afterEach(() => {
  window.sessionStorage.clear();
});

test("loads legacy policy analysis data as insurance documents", () => {
  window.sessionStorage.setItem(
    "coverly.policyAnalysis",
    JSON.stringify({
      generatedAt: "2026-07-11T00:00:00.000Z",
      policies: [
        {
          id: "legacy-insurance",
          fileName: "insurance.pdf",
          result: { status: "accepted", 문자수: 100 },
        },
      ],
    }),
  );

  expect(loadInsuranceAnalysis()).toEqual({
    generatedAt: "2026-07-11T00:00:00.000Z",
    selectedName: undefined,
    insuranceDocuments: [
      {
        id: "legacy-insurance",
        fileName: "insurance.pdf",
        result: { status: "accepted", 문자수: 100 },
      },
    ],
  });
});
