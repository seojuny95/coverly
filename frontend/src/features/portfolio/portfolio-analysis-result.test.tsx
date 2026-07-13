import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PortfolioAnalysisResultView } from "./portfolio-analysis-result";
import type { PortfolioAnalysisResult } from "./portfolio-api";

const base: PortfolioAnalysisResult = {
  status: "complete",
  policy_count: 2,
  classification_count: 1,
  confirmed_total_count: 0,
  indemnity_coverage_count: 0,
  indemnity_duplicate_count: 1,
  excluded_coverage_count: 0,
  excluded_auto_policy_count: 0,
  age: 35,
  gender: "남성",
  life_stage: "사회초년기",
  prepared_coverages: ["암 진단비"],
  coverage_gaps: [{ category: "간병", reason: "확인되지 않았어요" }],
  excluded_coverages: [],
  premium: {
    monthly_total: 90_000,
    monthly_policy_count: 2,
    unconfirmed_policy_count: 0,
    items: [],
  },
  baseline_notice: "일반 참고 기준이에요.",
  classifications: [],
  sources: [{ insurer: "삼성화재", product_name: "건강보험" }],
  notices: [],
};

describe("PortfolioAnalysisResultView", () => {
  it("renders the header with the insured name and headline metrics", () => {
    render(<PortfolioAnalysisResultView result={base} insuredName="가나" />);

    expect(screen.getByText(/Coverly AI가 가나님 편에서/)).toBeInTheDocument();
    expect(screen.getByText("35세 ·", { exact: false })).toBeInTheDocument();
    // formatWon(90000) monthly premium
    expect(screen.getByText("90,000원")).toBeInTheDocument();
  });

  it("falls back to prepared_coverages / coverage_gaps without a counselor", () => {
    render(<PortfolioAnalysisResultView result={base} />);
    expect(screen.getByText("암 진단비")).toBeInTheDocument();
    expect(screen.getByText("간병")).toBeInTheDocument();
    // fallback overview mentions the policy count
    expect(screen.getByText(/보험 2건에서/)).toBeInTheDocument();
  });

  it("prefers counselor strengths/gaps/overview when present", () => {
    const withCounselor: PortfolioAnalysisResult = {
      ...base,
      counselor: {
        overview: "전반적으로 잘 준비돼 있어요.",
        strengths: [
          {
            title: "실손 잘 가입됨",
            detail: "실손이 있어요",
            evidence_ids: [],
          },
        ],
        gaps: [
          {
            title: "간병 공백",
            detail: "지금 확인되지 않아요",
            evidence_ids: [],
          },
        ],
        amount_review_items: [],
        next_questions: ["간병은 어떻게 대비할까요?"],
        next_steps: [],
      },
    };
    render(<PortfolioAnalysisResultView result={withCounselor} />);

    expect(
      screen.getByText("전반적으로 잘 준비돼 있어요."),
    ).toBeInTheDocument();
    expect(screen.getByText("실손 잘 가입됨")).toBeInTheDocument();
    expect(screen.getByText("간병 공백")).toBeInTheDocument();
    // the prepared_coverages fallback is not used when counselor is present
    expect(screen.queryByText("암 진단비")).not.toBeInTheDocument();
  });
});
