import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CoverageTotalTable } from "./total-table";
import type { PortfolioSummary } from "./api";

const emptySummary: PortfolioSummary = {
  totals: [],
  actual_loss_coverages: [],
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
      screen.getByRole("status", {
        name: "보장금 합계를 불러오고 있어요.",
      }),
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

  it("shows progress and prevents duplicate clicks while retrying", () => {
    render(<CoverageTotalTable status="error" onRetry={vi.fn()} isRetrying />);

    const retryButton = screen.getByRole("button", {
      name: "다시 불러오는 중…",
    });
    expect(retryButton).toBeDisabled();
    expect(retryButton).toHaveAttribute("aria-busy", "true");
  });

  it("explains when loading the totals fails again", () => {
    render(<CoverageTotalTable status="error" onRetry={vi.fn()} retryFailed />);

    expect(screen.getByRole("alert")).toHaveTextContent(
      "보장금 합계를 다시 불러오지 못했어요. 잠시 후 다시 시도해주세요",
    );
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
                  policy_id: null,
                  product_name: "개인용자동차보험",
                  coverages: [
                    {
                      coverage_name: "대인배상Ⅰ",
                      original_amount: "무한",
                      major_category: "자동차",
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

  it("renders non-medical actual-loss coverage as coverage total data", () => {
    render(
      <CoverageTotalTable
        status="success"
        summary={{
          ...emptySummary,
          actual_loss_coverages: [
            {
              policy_id: null,
              insurer: null,
              product_name: null,
              coverage_name: "일상생활배상책임",
              normalized_name: "일상생활배상책임",
              original_amount: "",
              major_category: "배상책임",
              coverage_domain: "liability",
              is_medical_indemnity: false,
              is_damage_policy: false,
              duplicate_across_contracts: false,
            },
          ],
        }}
        onRetry={vi.fn()}
      />,
    );

    expect(screen.getByText("일상생활배상책임")).toBeInTheDocument();
    expect(screen.getAllByText("실손 보장")).toHaveLength(2);
  });

  it("does not duplicate damage-policy actual-loss coverage in the total", () => {
    render(
      <CoverageTotalTable
        status="success"
        summary={{
          ...emptySummary,
          actual_loss_coverages: [
            {
              policy_id: null,
              insurer: null,
              product_name: null,
              coverage_name: "자동차사고벌금",
              normalized_name: "자동차사고벌금",
              original_amount: "",
              major_category: "운전자",
              coverage_domain: "legal_cost",
              is_medical_indemnity: false,
              is_damage_policy: true,
              duplicate_across_contracts: false,
            },
          ],
        }}
        onRetry={vi.fn()}
      />,
    );

    expect(
      screen.getByText("표시할 보장금액을 찾지 못했어요."),
    ).toBeInTheDocument();
    expect(screen.queryByText("자동차사고벌금")).not.toBeInTheDocument();
  });
});
