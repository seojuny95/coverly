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
    const { container } = renderWithProviders(<InsuranceAnalysisPage />, {
      initialAnalysis: fixture(),
    });

    await screen.findByText("1,000만원");
    const text = container.textContent ?? "";
    expect(text.indexOf("상해·질병·실손")).toBeLessThan(
      text.indexOf("보험금 합계"),
    );
    expect(text.indexOf("보험금 합계")).toBeLessThan(text.indexOf("건강보험"));
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
              majorCategory: "진단비",
              totalAmount: 150_001_000,
              coverageCount: 2,
              normalizedName: "암진단비",
              composition: [],
            },
            {
              category: "통원비",
              majorCategory: "통원",
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
    expect(screen.getByText("2개 합산")).toBeInTheDocument();
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

    renderWithProviders(<InsuranceAnalysisPage />, {
      initialAnalysis: fixture(),
    });

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

  test("keeps chat messages between the floating chat and 상담 tab", async () => {
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
            indemnity_coverage_count: 0,
            indemnity_duplicate_count: 1,
            excluded_coverages: [
              {
                coverage_name: "알 수 없는 담보",
                reason: "담보명을 분류하지 못해 합계에는 더하지 않았어요.",
              },
            ],
            premium: {
              monthly_total: 80000,
              monthly_policy_count: 2,
              unconfirmed_policy_count: 0,
              items: [],
            },
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
        }),
      );
    });
    vi.stubGlobal("fetch", fetchMock);
    renderWithProviders(<InsuranceAnalysisPage />, {
      initialAnalysis: fixture(),
    });

    await user.click(await screen.findByRole("tab", { name: /보험 분석/ }));
    await screen.findByText("Coverly AI가 당신 편에서 살펴봤어요");
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/portfolio/analysis"),
      expect.objectContaining({
        method: "POST",
        body: expect.stringContaining('"source":"policy"'),
      }),
    );

    await user.click(
      screen.getByRole("button", { name: "AI 상담사에게 질문하기" }),
    );
    await user.type(screen.getByLabelText("보험 질문"), "암 진단비는?");
    await user.click(screen.getByRole("button", { name: "질문하기" }));
    expect(
      await screen.findByText("암 진단비는 1,000만원이에요."),
    ).toBeInTheDocument();
    expect(screen.queryByText("중복되면 안 되는 요약")).not.toBeInTheDocument();
    expect(
      screen.getByText("증권에서 암 진단비를 확인했어요."),
    ).toBeInTheDocument();
    expect(screen.getByText("매달 내는 보험료")).toBeInTheDocument();
    expect(screen.getByText("80,000원")).toBeInTheDocument();
    expect(
      screen.getByText(/중복 수령이 안 되는데 겹쳐 가입된 보장 1건/),
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

  test("shows the analysis badge while pending and runs analysis once across tab switches", async () => {
    const user = userEvent.setup();
    let resolveAnalysis: ((value: Response) => void) | undefined;
    const analysisPromise = new Promise<Response>((resolve) => {
      resolveAnalysis = resolve;
    });
    const analysisResponse = () =>
      new Response(
        JSON.stringify({
          status: "complete",
          policy_count: 1,
          classification_count: 1,
          confirmed_total_count: 1,
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
          counselor: {
            overview: "상담 전에 확인한 요약이에요.",
            strengths: [],
            gaps: [],
            amount_review_items: [],
            next_questions: [],
            next_steps: [],
          },
          notices: [],
        }),
      );

    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      if (String(input).endsWith("/portfolio/analysis")) return analysisPromise;
      return Promise.resolve(
        new Response(
          JSON.stringify({
            totals: [],
            indemnity_coverages: [],
            excluded_coverages: [],
            excluded_auto_policy_count: 0,
          }),
        ),
      );
    });
    vi.stubGlobal("fetch", fetchMock);
    renderWithProviders(<InsuranceAnalysisPage />, {
      initialAnalysis: fixture(),
    });

    // Analysis starts on 내 보험 entry; the 보험 분석 tab shows a pending badge.
    expect(await screen.findByText("분석 중…")).toBeInTheDocument();
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/portfolio/analysis"),
        expect.anything(),
      ),
    );

    resolveAnalysis?.(analysisResponse());
    await waitFor(() =>
      expect(screen.queryByText("분석 중…")).not.toBeInTheDocument(),
    );

    // Switching service tabs back and forth reuses the cached result.
    await user.click(screen.getByRole("tab", { name: "보험 분석" }));
    expect(
      await screen.findByText("상담 전에 확인한 요약이에요."),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "내 보험" }));
    await user.click(screen.getByRole("tab", { name: "보험 분석" }));

    const analysisCalls = (
      fetchMock.mock.calls as unknown as Array<[RequestInfo | URL, RequestInit]>
    ).filter(([input]) => String(input).endsWith("/portfolio/analysis"));
    expect(analysisCalls).toHaveLength(1);
  });

  test("asks for demographics only when policy demographics are missing", async () => {
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
    expect(screen.getByLabelText("나이")).toBeInTheDocument();
    expect(screen.getByLabelText("성별")).toBeInTheDocument();
  });

  test("sends auto policies so the backend can report their exclusion", async () => {
    const analysis = fixture();
    analysis.insuranceDocuments.push({
      id: "auto-1",
      fileName: "auto.pdf",
      result: {
        status: "accepted",
        문자수: 50,
        기본정보: { 보험분류: "자동차" },
        보장목록: [],
      },
    });
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).endsWith("/portfolio/analysis")) {
        return new Response(
          JSON.stringify({
            status: "complete",
            policy_count: 1,
            classification_count: 1,
            confirmed_total_count: 0,
            indemnity_coverage_count: 0,
            indemnity_duplicate_count: 0,
            excluded_coverages: [],
            premium: {
              monthly_total: 0,
              monthly_policy_count: 0,
              unconfirmed_policy_count: 0,
              items: [],
            },
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
    renderWithProviders(<InsuranceAnalysisPage />, {
      initialAnalysis: analysis,
    });

    await user.click(await screen.findByRole("tab", { name: /보험 분석/ }));
    await screen.findByText("Coverly AI가 당신 편에서 살펴봤어요");
    const fetchCalls = fetchMock.mock.calls as unknown as Array<
      [RequestInfo | URL, RequestInit]
    >;
    const analysisCall = fetchCalls.find(([input]) =>
      String(input).endsWith("/portfolio/analysis"),
    );
    expect(analysisCall?.[1]?.body).toContain("auto-1");
  });
});
