import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SamplePortfolioNotice } from "./sample-notice";
import { renderWithProviders } from "../../../test/render-with-providers";
import { POLICY_RESULT_DEFAULTS } from "../../../test/api-fixtures";

describe("SamplePortfolioNotice", () => {
  it("labels sample analysis and offers a real-policy path", () => {
    renderWithProviders(<SamplePortfolioNotice />, {
      initialAnalysis: {
        generatedAt: "2026-08-14T00:00:00.000Z",
        portfolioKind: "sample",
        portfolioSessionToken: "sample-token",
        portfolioSessionExpiresAt: "2030-01-01T00:00:00.000Z",
        counselTurnsRemaining: 10,
        insuranceDocuments: [
          {
            id: "00000000-0000-0000-0000-000000000001",
            fileName: "sample.pdf",
            result: POLICY_RESULT_DEFAULTS,
          },
        ],
      },
    });

    expect(
      screen.getByText("샘플 보험 데이터로 확인하고 있어요"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "내 증권으로 분석하기" }),
    ).toHaveAttribute("href", "/upload");
  });
});
