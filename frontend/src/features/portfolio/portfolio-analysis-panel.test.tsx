import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { PortfolioAnalysisPanel } from "./portfolio-analysis-panel";
import type { PortfolioAnalysisResult } from "./portfolio-api";

const noop = () => {};

function baseProps() {
  return {
    status: "idle" as const,
    result: undefined,
    eligibleCount: 1,
    emptyReason: "no-coverage" as const,
    needsDemographics: false,
    onManualDemographics: noop,
    onRetry: noop,
  };
}

test("shows the auto-only empty copy when no eligible documents", () => {
  render(
    <PortfolioAnalysisPanel
      {...baseProps()}
      eligibleCount={0}
      emptyReason="auto-only"
    />,
  );

  expect(screen.getByText("분석할 보험이 없어요")).toBeInTheDocument();
  expect(
    screen.getByText(/자동차보험은 이번 분석에서 제외해요/),
  ).toBeInTheDocument();
});

test("shows the no-coverage empty copy when no eligible documents", () => {
  render(
    <PortfolioAnalysisPanel
      {...baseProps()}
      eligibleCount={0}
      emptyReason="no-coverage"
    />,
  );

  expect(screen.getByText("분석할 보험이 없어요")).toBeInTheDocument();
  expect(
    screen.getByText(/담보 내용이 확인된 증권만 분석할 수 있어요\./),
  ).toBeInTheDocument();
});

test("asks for demographics when they are needed", () => {
  render(<PortfolioAnalysisPanel {...baseProps()} needsDemographics />);

  expect(screen.getByLabelText("나이")).toBeInTheDocument();
  expect(screen.getByLabelText("성별")).toBeInTheDocument();
});

test("shows the loading state while analysis runs", () => {
  render(<PortfolioAnalysisPanel {...baseProps()} status="loading" />);

  expect(
    screen.getByText("당신 편에서 보험을 살펴보고 있어요"),
  ).toBeInTheDocument();
});

test("renders the result view on success", () => {
  const result = {
    status: "complete",
    policy_count: 1,
    classification_count: 1,
    confirmed_total_count: 0,
    indemnity_coverage_count: 0,
    indemnity_duplicate_count: 0,
    excluded_coverage_count: 0,
    excluded_auto_policy_count: 0,
    age: 35,
    gender: "여성",
    life_stage: "성인",
    prepared_coverages: [],
    coverage_gaps: [],
    excluded_coverages: [],
    premium: {
      monthly_total: 0,
      monthly_policy_count: 0,
      unconfirmed_policy_count: 0,
      items: [],
    },
    baseline_notice: "참고 정보예요.",
    classifications: [],
    sources: [{ product_name: "테스트건강보험" }],
    notices: [],
    counselor: {
      overview: "상담 전에 확인한 요약이에요.",
      strengths: [],
      gaps: [],
      amount_review_items: [],
      next_questions: [],
      next_steps: [],
    },
  } as unknown as PortfolioAnalysisResult;

  render(
    <PortfolioAnalysisPanel
      {...baseProps()}
      status="success"
      result={result}
      insuredName="다라"
    />,
  );

  expect(
    screen.getByText("Coverly가 다라님 편에서 살펴봤어요"),
  ).toBeInTheDocument();
  expect(screen.getByText("상담 전에 확인한 요약이에요.")).toBeInTheDocument();
  expect(screen.getByText("테스트건강보험")).toBeInTheDocument();
});

test("calls onRetry from the error state", async () => {
  const onRetry = vi.fn();
  const { default: userEvent } = await import("@testing-library/user-event");
  const user = userEvent.setup();
  render(
    <PortfolioAnalysisPanel
      {...baseProps()}
      status="error"
      onRetry={onRetry}
    />,
  );

  await user.click(screen.getByRole("button", { name: "다시 분석하기" }));
  expect(onRetry).toHaveBeenCalledTimes(1);
});
