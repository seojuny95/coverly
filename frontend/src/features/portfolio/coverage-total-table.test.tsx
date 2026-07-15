import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CoverageTotalTable } from "./coverage-total-table";
import type { PortfolioSummary } from "./portfolio-api";

const emptySummary: PortfolioSummary = {
  totals: [],
  indemnity_coverages: [],
  excluded_coverages: [],
  excluded_auto_policy_count: 0,
};

const summaryWithData: PortfolioSummary = {
  ...emptySummary,
  totals: [
    {
      category: "암진단비",
      majorCategory: "진단",
      totalAmount: 30_000_000,
      coverageCount: 2,
      normalizedName: "암진단비",
      composition: [],
    },
  ],
};

describe("CoverageTotalTable", () => {
  it("shows a loading state", () => {
    render(<CoverageTotalTable status="loading" onRetry={vi.fn()} />);
    expect(
      screen.getByText("보장금 합계를 불러오고 있어요."),
    ).toBeInTheDocument();
  });

  it("shows an error state with a working retry", () => {
    const onRetry = vi.fn();
    render(<CoverageTotalTable status="error" onRetry={onRetry} />);
    expect(
      screen.getByText("보장금 합계를 불러오지 못했어요."),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "다시 불러오기" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("shows an empty message when success has no coverages", () => {
    render(
      <CoverageTotalTable
        status="success"
        summary={emptySummary}
        onRetry={vi.fn()}
      />,
    );
    expect(
      screen.getByText("표시할 보장금액을 찾지 못했어요."),
    ).toBeInTheDocument();
  });

  it("does not treat damage-only coverages as coverage total data", () => {
    render(
      <CoverageTotalTable
        status="success"
        summary={{
          ...emptySummary,
          damage_coverages: [
            {
              insurance_type: "자동차보험",
              policies: [
                {
                  product_name: "개인용자동차보험",
                  coverages: [
                    {
                      coverage_name: "대인배상Ⅰ",
                      original_amount: "무한",
                    },
                  ],
                },
              ],
            },
          ],
        }}
        onRetry={vi.fn()}
      />,
    );

    expect(
      screen.getByText("표시할 보장금액을 찾지 못했어요."),
    ).toBeInTheDocument();
    expect(screen.queryByText("대인배상Ⅰ")).not.toBeInTheDocument();
  });

  it("renders the coverage table when success has data", () => {
    render(
      <CoverageTotalTable
        status="success"
        summary={summaryWithData}
        onRetry={vi.fn()}
      />,
    );
    expect(screen.getByText("암진단비")).toBeInTheDocument();
    expect(
      screen.queryByText("표시할 보장금액을 찾지 못했어요."),
    ).not.toBeInTheDocument();
  });
});
