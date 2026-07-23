import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { CoverageSummaryTable } from "./summary-table";
import type { PortfolioSummary } from "./api";

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
          policy_id: null,
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
      policy_id: null,
      coverage_name: "실손입원",
      normalized_name: "실손입원",
      original_amount: "5,000만원",
      insurer: "현대해상",
      product_name: "실손의료보험",
      major_category: "치료",
      coverage_domain: "medical_expense",
      is_medical_indemnity: true,
      is_damage_policy: false,
      duplicate_across_contracts: true,
      guidance_key: "inpatient_medical_expense",
      explanation:
        "입원 치료 과정에서 실제로 부담한 의료비를 약관 한도 안에서 보상하는 담보예요.",
      explanation_basis: "generated_guidance",
    },
  ],
  excluded_coverages: [
    {
      policy_id: null,
      coverage_name: "기타특약",
      original_amount: "",
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
    expect(screen.getByText("2개 합산")).toBeInTheDocument();
  });

  it("labels actual-loss coverage separately from fixed-benefit totals", () => {
    render(<CoverageSummaryTable summary={summary} />);
    expect(screen.getByText("실손입원")).toBeInTheDocument();
    expect(screen.getByText("실손 보장")).toBeInTheDocument();
    expect(screen.getByText("중복 확인")).toBeInTheDocument();
  });

  it("groups duplicated actual-loss coverages by normalized name", () => {
    render(
      <CoverageSummaryTable
        summary={{
          ...summary,
          actual_loss_coverages: [
            {
              ...summary.actual_loss_coverages[0],
              policy_id: "injury-1",
              coverage_name: "상해실손의료비",
              normalized_name: "상해실손의료비",
              insurer: "보험사A",
              product_name: "실손보험 A",
              duplicate_across_contracts: true,
            },
            {
              ...summary.actual_loss_coverages[0],
              policy_id: "injury-2",
              coverage_name: "상해실손의료비",
              normalized_name: "상해실손의료비",
              insurer: "보험사B",
              product_name: "실손보험 B",
              duplicate_across_contracts: true,
            },
            {
              ...summary.actual_loss_coverages[0],
              policy_id: "illness-1",
              coverage_name: "질병실손의료비",
              normalized_name: "질병실손의료비",
              insurer: "보험사A",
              product_name: "실손보험 A",
              duplicate_across_contracts: false,
            },
          ],
        }}
      />,
    );

    expect(screen.getAllByText("상해실손의료비")).toHaveLength(1);
    expect(screen.getByText("질병실손의료비")).toBeInTheDocument();
    expect(
      screen.getByText("같은 실손형 담보가 여러 계약에서 확인됐어요."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("보험사A · 실손보험 A · 상해실손의료비 · 5,000만원"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("보험사B · 실손보험 B · 상해실손의료비 · 5,000만원"),
    ).toBeInTheDocument();
  });

  it("includes non-medical actual-loss coverage under the same basis", () => {
    render(
      <CoverageSummaryTable
        summary={{
          ...summary,
          actual_loss_coverages: [
            {
              ...summary.actual_loss_coverages[0],
              coverage_name: "일상생활배상책임",
              normalized_name: "일상생활배상책임",
              coverage_domain: "liability",
              is_medical_indemnity: false,
              duplicate_across_contracts: false,
            },
          ],
        }}
      />,
    );

    expect(screen.getByText("일상생활배상책임")).toBeInTheDocument();
    expect(screen.getByText("실손 보장")).toBeInTheDocument();
    expect(screen.queryByText("실손의료비")).not.toBeInTheDocument();
  });

  it("keeps damage-policy actual-loss coverage out of this table", () => {
    render(
      <CoverageSummaryTable
        summary={{
          ...summary,
          actual_loss_coverages: [
            {
              ...summary.actual_loss_coverages[0],
              coverage_name: "자동차사고벌금",
              normalized_name: "자동차사고벌금",
              coverage_domain: "legal_cost",
              is_medical_indemnity: false,
              is_damage_policy: true,
            },
          ],
        }}
      />,
    );

    expect(screen.queryByText("자동차사고벌금")).not.toBeInTheDocument();
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

  it("sorts categories by the coverage map display order", () => {
    render(
      <CoverageSummaryTable
        summary={{
          ...summary,
          totals: [
            { ...summary.totals[0], majorCategory: "기타" },
            {
              ...summary.totals[0],
              category: "사망보험금",
              normalizedName: "사망보험금",
              majorCategory: "사망",
            },
          ],
        }}
      />,
    );

    const categoryGroups = screen
      .getAllByRole("rowgroup")
      .map((group) => group.getAttribute("aria-label"))
      .filter(Boolean);
    expect(categoryGroups).toEqual(["사망", "치료", "기타"]);
  });

  it("keeps amount columns top-aligned when a row is expanded", () => {
    render(<CoverageSummaryTable summary={summary} />);

    expect(screen.getByRole("table")).toHaveClass("table-fixed");
    expect(screen.getByText("3,000만원").closest("td")).toHaveClass(
      "align-top",
    );
    expect(screen.getByText("2개 합산").closest("td")).toHaveClass("align-top");
  });

  it("animates coverage details when a row is expanded and collapsed", async () => {
    const user = userEvent.setup();
    render(<CoverageSummaryTable summary={summary} />);

    const trigger = screen.getByRole("button", { name: "암진단비" });
    const panel = document.getElementById(
      trigger.getAttribute("aria-controls") ?? "",
    );
    const collapseRegion = panel?.parentElement?.parentElement;

    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(collapseRegion).toHaveClass("grid-rows-[0fr]");

    await user.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(collapseRegion).toHaveClass("grid-rows-[1fr]");
    expect(panel?.firstElementChild).toHaveClass("opacity-100");

    await user.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(collapseRegion).toHaveClass("grid-rows-[0fr]");
    expect(panel?.firstElementChild).toHaveClass("opacity-0");
  });
});
