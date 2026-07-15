import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

// InsuranceAnalysisPage's header logo now guards leaving via LeaveGuardLink,
// which calls useRouter — mock it so it doesn't need a real App Router.
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), prefetch: vi.fn() }),
}));

import { renderWithProviders } from "../../test-utils/render-with-providers";
import { InsuranceAnalysisPage } from "../insurance-analysis/insurance-analysis-page";
import type { InsuranceAnalysis } from "../insurance-analysis/insurance-analysis-store";
import { CoverageSummaryTable } from "./coverage-summary-table";

function fixture(): InsuranceAnalysis {
  return {
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
            보험분류: "제3보험",
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
  };
}

describe("portfolio features", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  test("shows counts, totals, and cards in order", async () => {
    const fetchMock = vi.fn().mockImplementation(
      () =>
        new Response(
          JSON.stringify({
            totals: [
              {
                category: "암 진단비",
                majorCategory: "진단",
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
    const { container } = renderWithProviders(<InsuranceAnalysisPage />, {
      initialAnalysis: fixture(),
    });

    await screen.findByText("1,000만원");
    const text = container.textContent ?? "";
    expect(text.indexOf("제3보험")).toBeLessThan(text.indexOf("보장금 합계"));
    expect(text.indexOf("보장금 합계")).toBeLessThan(text.indexOf("건강보험"));
    expect(screen.getByText("1,000만원")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/portfolio/summary"),
      expect.objectContaining({ body: expect.stringContaining('"policies"') }),
    );
  });

  test("formats summed coverage amounts with Korean units", async () => {
    render(
      <CoverageSummaryTable
        summary={{
          totals: [
            {
              category: "암 진단비",
              majorCategory: "진단",
              totalAmount: 150_001_000,
              coverageCount: 2,
              normalizedName: "암진단비",
              composition: [],
            },
            {
              category: "통원비",
              majorCategory: "치료",
              totalAmount: 3_000,
              coverageCount: 1,
              normalizedName: "통원비",
              composition: [],
            },
          ],
          indemnity_coverages: [],
          excluded_coverages: [],
          excluded_auto_policy_count: 0,
        }}
      />,
    );

    expect(screen.getByText("1억 5,000만원 1천원")).toBeInTheDocument();
    expect(screen.getByText("3천원")).toBeInTheDocument();
    expect(screen.getByText("정액보상 · 2개 합산")).toBeInTheDocument();
  });

  test("groups every amount basis under the same coverage category", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(
        () =>
          new Response(
            JSON.stringify({
              totals: [
                {
                  category: "암치료비",
                  majorCategory: "치료",
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
                  major_category: "치료",
                  cross_insurer_duplicate: true,
                },
              ],
              excluded_coverages: [
                {
                  policy_id: "health-1",
                  insurer: "보험사A",
                  product_name: "건강보험",
                  coverage_name: "특정치료비",
                  major_category: "치료",
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

    renderWithProviders(<InsuranceAnalysisPage />, {
      initialAnalysis: fixture(),
    });

    const treatmentGroup = await screen.findByRole("rowgroup", {
      name: "치료",
    });
    const otherGroup = screen.getByRole("rowgroup", { name: "기타" });
    expect(within(treatmentGroup).getByText("암치료비")).toBeInTheDocument();
    expect(
      within(treatmentGroup).getByText(/질병실손의료비/),
    ).toBeInTheDocument();
    expect(within(treatmentGroup).getByText("특정치료비")).toBeInTheDocument();
    expect(within(treatmentGroup).getByText("정액보상")).toBeInTheDocument();
    expect(within(treatmentGroup).getByText("실손의료")).toBeInTheDocument();
    expect(within(treatmentGroup).getByText("개별 확인")).toBeInTheDocument();
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
      screen.getByRole("table", { name: "보장금 합계" }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/합산하지 않은 담보/)).not.toBeInTheDocument();
  });

  test("keeps chat messages between the floating chat and 상담 tab", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path.endsWith("/qa/stream")) {
        const events = [
          { type: "meta", status: "answered", generation: "llm" },
          { type: "delta", text: "암 진단비는 1,000만원이에요." },
          {
            type: "end",
            status: "answered",
            generation: "llm",
            citations: [],
            limitations: [],
            suggestions: [],
            claim_channels: null,
          },
        ];
        const body = events
          .map((event) => `data: ${JSON.stringify(event)}\n\n`)
          .join("");
        return new Response(body, {
          headers: { "Content-Type": "text/event-stream" },
        });
      }
      return new Response(
        JSON.stringify({
          totals: [],
          indemnity_coverages: [],
          excluded_coverages: [],
          excluded_auto_policy_count: 0,
          overview: {
            generation: "llm",
            title: "현재 보장을 한눈에 확인해보세요",
            paragraphs: ["확인된 보장 정보를 바탕으로 정리했어요."],
            takeaways: [],
          },
          essential_coverage_check: {
            items: [
              {
                kind: "cancer",
                label: "암 진단비",
                status: "needs_review",
                confirmed_amount: 10_000_000,
                reference_min_amount: 30_000_000,
                reference_max_amount: 50_000_000,
                reference_basis:
                  "암 진단비는 치료 중 쉬는 기간의 생활비 성격까지 고려하는 기본 범위",
                reference_sources: [
                  {
                    label: "비즈워치 · 암 진단비 평균 범위",
                    url: "https://news.bizwatch.co.kr/article/finance/2024/07/05/0038",
                    published_at: "2024-07-06",
                    reliability: "private_guidance",
                    caveat:
                      "암 진단비 금액은 소득, 가족 부양, 보험료 부담에 따라 달라질 수 있어요.",
                  },
                ],
                coverage_count: 1,
                detail:
                  "일반암 진단비는 확인되지만 가입금액이 참고금액보다 낮아요.",
                matched_coverage_names: ["암 진단비"],
              },
            ],
          },
        }),
      );
    });
    vi.stubGlobal("fetch", fetchMock);
    renderWithProviders(<InsuranceAnalysisPage />, {
      initialAnalysis: fixture(),
    });

    await user.click(await screen.findByRole("tab", { name: /보험 분석/ }));
    await screen.findByText("권장보험");
    expect(fetchMock).not.toHaveBeenCalledWith(
      expect.stringContaining("/portfolio/analysis"),
      expect.anything(),
    );

    await user.click(
      screen.getByRole("button", { name: "AI 상담사에게 질문하기" }),
    );
    await user.type(screen.getByLabelText("보험 질문"), "암 진단비는?");
    await user.click(screen.getByRole("button", { name: "질문하기" }));
    expect(
      await screen.findByText("암 진단비는 1,000만원이에요."),
    ).toBeInTheDocument();
    const fetchCalls = fetchMock.mock.calls as unknown as Array<
      [RequestInfo | URL, RequestInit]
    >;
    const qaCall = fetchCalls.find(([input]) =>
      String(input).endsWith("/qa/stream"),
    );
    expect(qaCall?.[1]?.body).toContain('"history":[]');

    await user.click(
      screen.getByRole("button", { name: "AI 보험 상담 탭에서 크게 보기" }),
    );
    expect(screen.getByRole("tab", { name: "AI 보험 상담" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(
      screen.queryByRole("button", { name: "AI 보험 상담 탭에서 크게 보기" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText("암 진단비는 1,000만원이에요."),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "내 보험" }));
    expect(
      screen.getByText("암 진단비는 1,000만원이에요."),
    ).toBeInTheDocument();
  });

  test("shows the summary badge while pending and reuses it across tab switches", async () => {
    const user = userEvent.setup();
    let resolveSummary: ((value: Response) => void) | undefined;
    const summaryPromise = new Promise<Response>((resolve) => {
      resolveSummary = resolve;
    });
    const summaryResponse = () =>
      new Response(
        JSON.stringify({
          totals: [],
          indemnity_coverages: [],
          excluded_coverages: [],
          excluded_auto_policy_count: 0,
          essential_coverage_check: {
            items: [
              {
                kind: "cancer",
                label: "암 진단비",
                status: "well_prepared",
                confirmed_amount: 30_000_000,
                reference_min_amount: 30_000_000,
                reference_max_amount: 50_000_000,
                reference_basis:
                  "암 진단비는 치료 중 쉬는 기간의 생활비 성격까지 고려하는 기본 범위",
                reference_sources: [
                  {
                    label: "비즈워치 · 암 진단비 평균 범위",
                    url: "https://news.bizwatch.co.kr/article/finance/2024/07/05/0038",
                    published_at: "2024-07-06",
                    reliability: "private_guidance",
                    caveat:
                      "암 진단비 금액은 소득, 가족 부양, 보험료 부담에 따라 달라질 수 있어요.",
                  },
                ],
                coverage_count: 1,
                detail: "일반암 진단비가 참고금액 이상으로 확인돼요.",
                matched_coverage_names: ["암진단비"],
              },
            ],
          },
        }),
      );

    const fetchMock = vi.fn(() => summaryPromise);
    vi.stubGlobal("fetch", fetchMock);
    renderWithProviders(<InsuranceAnalysisPage />, {
      initialAnalysis: fixture(),
    });

    expect(await screen.findByText("분석 중…")).toBeInTheDocument();
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/portfolio/summary"),
        expect.anything(),
      ),
    );

    resolveSummary?.(summaryResponse());
    await waitFor(() =>
      expect(screen.queryByText("분석 중…")).not.toBeInTheDocument(),
    );

    await user.click(screen.getByRole("tab", { name: "보험 분석" }));
    expect(await screen.findByText("권장보험")).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "내 보험" }));
    await user.click(screen.getByRole("tab", { name: "보험 분석" }));

    const summaryCalls = (
      fetchMock.mock.calls as unknown as Array<[RequestInfo | URL, RequestInit]>
    ).filter(([input]) => String(input).endsWith("/portfolio/summary"));
    expect(summaryCalls).toHaveLength(1);
  });

  test("does not ask for demographics when policy demographics are missing", async () => {
    const analysis = fixture();
    delete analysis.insuranceDocuments[0].result.기본정보!.피보험자정보;
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
    renderWithProviders(<InsuranceAnalysisPage />, {
      initialAnalysis: analysis,
    });

    await user.click(await screen.findByRole("tab", { name: "보험 분석" }));
    await screen.findByText("권장보험");
    expect(screen.queryByLabelText("나이")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("성별")).not.toBeInTheDocument();
  });

  test("sends damage policies so the backend can list them separately", async () => {
    const analysis = fixture();
    analysis.insuranceDocuments.push({
      id: "auto-1",
      fileName: "auto.pdf",
      result: {
        status: "accepted",
        문자수: 50,
        기본정보: { 보험분류: "손해보험", 상품태그: ["자동차보험"] },
        보장목록: [],
      },
    });
    const fetchMock = vi.fn(async () => {
      return new Response(
        JSON.stringify({
          totals: [],
          indemnity_coverages: [],
          excluded_coverages: [],
          excluded_auto_policy_count: 1,
          essential_coverage_check: { items: [] },
        }),
      );
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderWithProviders(<InsuranceAnalysisPage />, {
      initialAnalysis: analysis,
    });

    await user.click(await screen.findByRole("tab", { name: /보험 분석/ }));
    await screen.findByText("권장보험");
    const fetchCalls = fetchMock.mock.calls as unknown as Array<
      [RequestInfo | URL, RequestInit]
    >;
    const summaryCall = fetchCalls.find(([input]) =>
      String(input).endsWith("/portfolio/summary"),
    );
    expect(summaryCall?.[1]?.body).toContain("auto-1");
  });
});
