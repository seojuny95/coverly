import { render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import type { AnalyzedInsurance } from "../insurance-analysis/insurance-analysis-store";
import { PortfolioAnalysisPanel } from "./portfolio-analysis-panel";

function document(id: string): AnalyzedInsurance {
  return {
    id,
    fileName: `${id}.pdf`,
    result: {
      status: "accepted",
      문자수: 100,
      기본정보: {
        보험분류: "상해·질병·실손",
        피보험자정보: { 나이: 35, 성별: "여성", 생애단계: "성인" },
      },
      보장목록: [],
    },
  };
}

function response(overview: string) {
  return new Response(
    JSON.stringify({
      status: "complete",
      policy_count: 1,
      classification_count: 1,
      confirmed_total_count: 0,
      confirmed_total_amount: 0,
      indemnity_coverage_count: 0,
      excluded_coverage_count: 0,
      excluded_auto_policy_count: 0,
      age: 35,
      gender: "여성",
      life_stage: "성인",
      prepared_coverages: [],
      coverage_gaps: [],
      baseline_notice: "참고 정보예요.",
      classifications: [],
      notices: [],
      counselor: {
        overview,
        strengths: [],
        gaps: [],
        amount_review_items: [],
        next_questions: [],
        next_steps: [],
      },
    }),
  );
}

afterEach(() => vi.unstubAllGlobals());

test("ignores an older analysis response after the portfolio changes", async () => {
  let resolveFirst: ((value: Response) => void) | undefined;
  let resolveSecond: ((value: Response) => void) | undefined;
  const first = new Promise<Response>((resolve) => {
    resolveFirst = resolve;
  });
  const second = new Promise<Response>((resolve) => {
    resolveSecond = resolve;
  });
  const fetchMock = vi
    .fn()
    .mockReturnValueOnce(first)
    .mockReturnValueOnce(second);
  vi.stubGlobal("fetch", fetchMock);
  const { rerender } = render(
    <PortfolioAnalysisPanel active documents={[document("first")]} />,
  );

  rerender(<PortfolioAnalysisPanel active documents={[document("second")]} />);
  resolveSecond?.(response("새 보험 기준 분석"));
  expect(await screen.findByText("새 보험 기준 분석")).toBeInTheDocument();

  resolveFirst?.(response("이전 보험 기준 분석"));
  await Promise.resolve();
  expect(screen.queryByText("이전 보험 기준 분석")).not.toBeInTheDocument();
});

test("asks for confirmation when policies contain conflicting demographics", () => {
  const first = document("first");
  const second = document("second");
  second.result.기본정보!.피보험자정보 = {
    나이: 42,
    성별: "남성",
    생애단계: "성인",
  };
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);

  render(<PortfolioAnalysisPanel active documents={[first, second]} />);

  expect(screen.getByLabelText("나이")).toBeInTheDocument();
  expect(screen.getByLabelText("성별")).toBeInTheDocument();
  expect(fetchMock).not.toHaveBeenCalled();
});
