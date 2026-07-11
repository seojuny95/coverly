import { render, screen, within } from "@testing-library/react";
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
            피보험자정보: {
              나이: 35,
              성별: "여성",
              생애단계: "성인",
            },
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
    const fetchMock = vi.fn().mockImplementation(
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
    );
    vi.stubGlobal("fetch", fetchMock);
    const { container } = render(<InsuranceAnalysisPage />);

    await screen.findByText("10,000,000원");
    const text = container.textContent ?? "";
    expect(text.indexOf("상해·질병·실손")).toBeLessThan(
      text.indexOf("보험금 합계"),
    );
    expect(text.indexOf("보험금 합계")).toBeLessThan(text.indexOf("건강보험"));
    expect(screen.getByText("10,000,000원")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/portfolio/summary"),
      expect.objectContaining({ body: expect.stringContaining('"policies"') }),
    );
  });

  test("groups every amount basis under the same coverage category", async () => {
    saveFixture();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(
        () =>
          new Response(
            JSON.stringify({
              totals: [
                {
                  category: "암치료비",
                  majorCategory: "치료비",
                  totalAmount: 10_000_000,
                  coverageCount: 1,
                  normalizedName: "암치료비",
                  composition: [],
                },
              ],
              indemnity_coverages: [
                {
                  policy_id: "health-1",
                  insurer: "보험사A",
                  product_name: "건강보험",
                  coverage_name: "질병실손의료비",
                  original_amount: "5천만원",
                  major_category: "치료비",
                  cross_insurer_duplicate: true,
                },
              ],
              excluded_coverages: [
                {
                  policy_id: "health-1",
                  insurer: "보험사A",
                  product_name: "건강보험",
                  coverage_name: "특정치료비",
                  major_category: "치료비",
                  original_amount: "1천만원",
                  reason: "지급 방식을 확인하지 못해 합계에는 더하지 않았어요.",
                },
                {
                  policy_id: "health-1",
                  coverage_name: "생활보장",
                  reason: "지급 방식을 확인하지 못해 합계에는 더하지 않았어요.",
                },
              ],
              excluded_auto_policy_count: 0,
            }),
          ),
      ),
    );

    render(<InsuranceAnalysisPage />);

    const treatmentGroup = await screen.findByRole("rowgroup", {
      name: "치료비",
    });
    const otherGroup = screen.getByRole("rowgroup", { name: "기타" });
    expect(within(treatmentGroup).getByText("암치료비")).toBeInTheDocument();
    expect(
      within(treatmentGroup).getByText(/질병실손의료비/),
    ).toBeInTheDocument();
    expect(within(treatmentGroup).getByText("특정치료비")).toBeInTheDocument();
    expect(
      within(treatmentGroup).getByText("합산 보장금액"),
    ).toBeInTheDocument();
    expect(within(treatmentGroup).getByText("실손형 보장")).toBeInTheDocument();
    expect(
      within(treatmentGroup).getByText("그대로 보는 보장"),
    ).toBeInTheDocument();
    for (const coverageName of ["암치료비", "질병실손의료비", "특정치료비"]) {
      const disclosure = within(treatmentGroup)
        .getByText(coverageName)
        .closest("details");
      expect(disclosure).toBeInTheDocument();
      expect(disclosure).not.toHaveAttribute("open");
    }
    expect(within(otherGroup).getByText("생활보장")).toBeInTheDocument();
    expect(
      within(otherGroup).getByText(/보험사 확인 필요/),
    ).toBeInTheDocument();
    expect(within(otherGroup).getByText("금액 확인 필요")).toBeInTheDocument();
    expect(
      screen.getAllByText(
        "지급 방식을 확인하지 못해 합계에는 더하지 않았어요.",
      ),
    ).toHaveLength(2);
    expect(
      screen.getByRole("table", { name: "보험금 합계" }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/합산하지 않은 담보/)).not.toBeInTheDocument();
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
            counselor: {
              overview: "상담 전에 확인한 요약이에요.",
              strengths: [
                {
                  title: "암 진단 보장",
                  detail: "증권에서 암 진단비를 확인했어요.",
                  evidence_ids: ["e1"],
                },
              ],
              gaps: [],
              amount_review_items: [
                {
                  coverage_name: "암 진단비",
                  current_amount: 10_000_000,
                  title: "암 진단비 금액",
                  guidance: "생활비와 함께 확인해보세요.",
                  rationale: "현재 금액만으로 적정성을 판단하지 않아요.",
                  suggested_range: null,
                  confidence: "medium",
                  evidence_ids: ["e1"],
                },
              ],
              next_questions: [],
              next_steps: [],
            },
            notices: [],
          }),
        );
      }
      if (path.endsWith("/qa")) {
        return new Response(
          JSON.stringify({
            status: "answered",
            answer: "중복되면 안 되는 요약",
            sections: [
              {
                title: "확인된 보장",
                content: "암 진단비는 1,000만원이에요.",
                basis: "confirmed_fact",
              },
            ],
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
    expect((await screen.findAllByText("10,000,000원")).length).toBeGreaterThan(
      0,
    );
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/portfolio/analysis"),
      expect.objectContaining({
        method: "POST",
        body: expect.stringContaining('"source":"policy"'),
      }),
    );

    await user.click(
      screen.getByRole("button", { name: "내 보험에 질문하기" }),
    );
    await user.type(screen.getByLabelText("보험 질문"), "암 진단비는?");
    await user.click(screen.getByRole("button", { name: "질문하기" }));
    expect(
      await screen.findByText(/확인된 보장\s+암 진단비는 1,000만원이에요\./),
    ).toBeInTheDocument();
    expect(screen.queryByText("중복되면 안 되는 요약")).not.toBeInTheDocument();
    expect(
      screen.getByText("증권에서 암 진단비를 확인했어요."),
    ).toBeInTheDocument();
    expect(screen.getByText("암 진단비 금액")).toBeInTheDocument();
    expect(screen.getByText("생활비와 함께 확인해보세요.")).toBeInTheDocument();
    expect(screen.getByText(/보통 확신/)).toBeInTheDocument();
    const fetchCalls = fetchMock.mock.calls as unknown as Array<
      [RequestInfo | URL, RequestInit]
    >;
    const qaCall = fetchCalls.find(([input]) => String(input).endsWith("/qa"));
    expect(qaCall?.[1]?.body).toContain('"history":[]');

    await user.click(screen.getByRole("tab", { name: "내 보험" }));
    expect(
      screen.getByText(/확인된 보장\s+암 진단비는 1,000만원이에요\./),
    ).toBeInTheDocument();
  });

  test("asks for demographics only when policy demographics are missing", async () => {
    saveFixture();
    const stored = JSON.parse(
      window.sessionStorage.getItem("coverly.insuranceAnalysis") ?? "{}",
    );
    delete stored.insuranceDocuments[0].result.기본정보.피보험자정보;
    window.sessionStorage.setItem(
      "coverly.insuranceAnalysis",
      JSON.stringify(stored),
    );
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            totals: [],
            indemnity_coverages: [],
            excluded_coverages: [],
            excluded_auto_policy_count: 0,
          }),
        ),
      ),
    );
    const user = userEvent.setup();
    render(<InsuranceAnalysisPage />);

    await user.click(await screen.findByRole("tab", { name: "보험 분석" }));
    expect(screen.getByLabelText("나이")).toBeInTheDocument();
    expect(screen.getByLabelText("성별")).toBeInTheDocument();
  });

  test("sends auto policies so the backend can report their exclusion", async () => {
    saveFixture();
    const stored = JSON.parse(
      window.sessionStorage.getItem("coverly.insuranceAnalysis") ?? "{}",
    );
    stored.insuranceDocuments.push({
      id: "auto-1",
      fileName: "auto.pdf",
      result: {
        status: "accepted",
        문자수: 50,
        기본정보: { 보험분류: "자동차" },
        보장목록: [],
      },
    });
    window.sessionStorage.setItem(
      "coverly.insuranceAnalysis",
      JSON.stringify(stored),
    );
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).endsWith("/portfolio/analysis")) {
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
          }),
        );
      }
      return new Response(
        JSON.stringify({
          totals: [],
          indemnity_coverages: [],
          excluded_coverages: [],
          excluded_auto_policy_count: 1,
        }),
      );
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<InsuranceAnalysisPage />);

    await user.click(await screen.findByRole("tab", { name: "보험 분석" }));
    await screen.findByText("Coverly가 당신 편에서 살펴봤어요");
    const fetchCalls = fetchMock.mock.calls as unknown as Array<
      [RequestInfo | URL, RequestInit]
    >;
    const analysisCall = fetchCalls.find(([input]) =>
      String(input).endsWith("/portfolio/analysis"),
    );
    expect(analysisCall?.[1]?.body).toContain("auto-1");
  });
});
