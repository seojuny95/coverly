import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { InsuranceAnalysisPage } from "../insurance-analysis/insurance-analysis-page";
import { saveInsuranceAnalysis } from "../insurance-analysis/insurance-analysis-store";

function saveFixture() {
  saveInsuranceAnalysis({
    generatedAt: "2026-07-11T00:00:00.000Z",
    insuranceDocuments: [
      {
        id: "health-1",
        fileName: "health.pdf",
        result: {
          status: "accepted",
          문자수: 100,
          기본정보: {
            상품명: "건강보험",
            보험분류: "상해·질병·실손",
          },
          보장목록: [
            {
              담보명: "암 진단비",
              가입금액: "1,000만원",
              보장내용: null,
              해설: null,
            },
          ],
        },
      },
    ],
  });
}

describe("portfolio features", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    window.sessionStorage.clear();
  });

  test("shows counts, totals, and cards in order", async () => {
    saveFixture();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(
        () =>
          new Response(
            JSON.stringify({
              totals: [
                {
                  category: "암 진단비",
                  majorCategory: "진단비",
                  totalAmount: 10_000_000,
                  coverageCount: 1,
                  normalizedName: "암진단비",
                  composition: [],
                },
              ],
              indemnity_coverages: [],
              excluded_coverages: [],
              excluded_auto_policy_count: 0,
            }),
          ),
      ),
    );
    const { container } = render(<InsuranceAnalysisPage />);

    await screen.findByText("10,000,000원");
    const text = container.textContent ?? "";
    expect(text.indexOf("상해·질병·실손")).toBeLessThan(
      text.indexOf("보험금 합계"),
    );
    expect(text.indexOf("보험금 합계")).toBeLessThan(text.indexOf("건강보험"));
    expect(screen.getByText("10,000,000원")).toBeInTheDocument();
  });

  test("starts analysis on first tab entry and keeps chat messages across tabs", async () => {
    saveFixture();
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path.endsWith("/portfolio/analysis")) {
        return new Response(
          JSON.stringify({
            status: "complete",
            policy_count: 1,
            classification_count: 1,
            confirmed_total_count: 1,
            confirmed_total_amount: 10_000_000,
            indemnity_coverage_count: 0,
            excluded_coverage_count: 0,
            excluded_auto_policy_count: 0,
            age: 35,
            gender: "여성",
            life_stage: "성인",
            prepared_coverages: ["암 진단"],
            coverage_gaps: [{ category: "뇌혈관 진단", reason: "확인 필요" }],
            baseline_notice: "참고 정보예요.",
            classifications: [
              {
                classification: "상해·질병·실손",
                policy_count: 1,
                confirmed_total_count: 1,
                confirmed_total_amount: 10_000_000,
                indemnity_coverage_count: 0,
                excluded_coverage_count: 0,
              },
            ],
            notices: [],
          }),
        );
      }
      if (path.endsWith("/qa")) {
        return new Response(
          JSON.stringify({
            status: "answered",
            answer: "암 진단비는 1,000만원이에요.",
            citations: [],
            limitations: [],
          }),
        );
      }
      return new Response(
        JSON.stringify({
          totals: [],
          indemnity_coverages: [],
          excluded_coverages: [],
          excluded_auto_policy_count: 0,
        }),
      );
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<InsuranceAnalysisPage />);

    await user.click(await screen.findByRole("tab", { name: "보험 분석" }));
    await user.type(screen.getByLabelText("나이"), "35");
    await user.selectOptions(screen.getByLabelText("성별"), "여성");
    await user.click(screen.getByRole("button", { name: "내 보험 분석하기" }));
    expect((await screen.findAllByText("10,000,000원")).length).toBeGreaterThan(
      0,
    );
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/portfolio/analysis"),
      expect.objectContaining({ method: "POST" }),
    );

    await user.click(
      screen.getByRole("button", { name: "내 보험에 질문하기" }),
    );
    await user.type(screen.getByLabelText("보험 질문"), "암 진단비는?");
    await user.click(screen.getByRole("button", { name: "질문하기" }));
    expect(
      await screen.findByText("암 진단비는 1,000만원이에요."),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "내 보험" }));
    expect(
      screen.getByText("암 진단비는 1,000만원이에요."),
    ).toBeInTheDocument();
  });
});
