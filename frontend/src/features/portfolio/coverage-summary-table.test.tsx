import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CoverageSummaryTable } from "./coverage-summary-table";
import type { PortfolioSummary } from "./portfolio-api";

const summary: PortfolioSummary = {
  totals: [
    {
      category: "암진단비",
      majorCategory: "진단",
      totalAmount: 30_000_000,
      coverageCount: 2,
      normalizedName: "암진단비",
      composition: [
        {
          insurer: "삼성화재",
          product_name: "건강보험",
          coverage_name: "암진단비",
          amount: 20_000_000,
          original_amount: "2,000만원",
        },
      ],
    },
  ],
  actual_loss_coverages: [
    {
      coverage_name: "실손입원",
      normalized_name: "실손입원",
      original_amount: "5,000만원",
      insurer: "현대해상",
      product_name: "실손의료보험",
      major_category: "치료",
      coverage_domain: "medical_expense",
      is_medical_indemnity: true,
      duplicate_across_contracts: true,
    },
  ],
  excluded_coverages: [
    {
      coverage_name: "기타특약",
      major_category: "기타",
      reason: "금액 기준을 확인하지 못했어요",
      insurer: "삼성화재",
    },
  ],
  excluded_auto_policy_count: 0,
};

describe("CoverageSummaryTable", () => {
  it("renders a summed coverage with its total and count basis", () => {
    render(<CoverageSummaryTable summary={summary} />);
    expect(screen.getByText("암진단비")).toBeInTheDocument();
    expect(screen.getByText("3,000만원")).toBeInTheDocument();
    expect(screen.getByText("정액보상 · 2개 합산")).toBeInTheDocument();
  });

  it("flags medical indemnity repeated across contracts for review", () => {
    render(<CoverageSummaryTable summary={summary} />);
    expect(screen.getByText("실손입원")).toBeInTheDocument();
    expect(screen.getByText("실손의료비")).toBeInTheDocument();
    expect(screen.getByText("중복 확인")).toBeInTheDocument();
  });

  it("renders an excluded coverage as an individually-viewed row", () => {
    render(<CoverageSummaryTable summary={summary} />);
    expect(screen.getByText("기타특약")).toBeInTheDocument();
    expect(screen.getByText("개별 확인")).toBeInTheDocument();
  });

  it("groups rows under their major category headers", () => {
    render(<CoverageSummaryTable summary={summary} />);
    expect(screen.getByRole("rowgroup", { name: "진단" })).toBeInTheDocument();
    expect(screen.getByRole("rowgroup", { name: "치료" })).toBeInTheDocument();
    expect(screen.getByRole("rowgroup", { name: "기타" })).toBeInTheDocument();
  });

  it("keeps amount columns top-aligned when a row is expanded", () => {
    render(<CoverageSummaryTable summary={summary} />);

    expect(screen.getByRole("table")).toHaveClass("table-fixed");
    expect(screen.getByText("3,000만원").closest("td")).toHaveClass(
      "align-top",
    );
    expect(screen.getByText("정액보상 · 2개 합산").closest("td")).toHaveClass(
      "align-top",
    );
  });
});
