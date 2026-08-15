import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, describe, expect, test, vi } from "vitest";

import { CoverageAnalysis } from "./coverage/analysis";
import { PolicyOverview } from "./policies/overview";
import type { InsuranceAnalysis } from "./session/store";
import { renderWithProviders } from "@/test/render-with-providers";
import { POLICY_RESULT_DEFAULTS } from "@/test/api-fixtures";

function fixture(): InsuranceAnalysis {
  return {
    generatedAt: "2026-07-11T00:00:00.000Z",
    portfolioKind: "uploaded" as const,
    portfolioSessionToken: "test-portfolio-token",
    portfolioSessionExpiresAt: "2030-01-01T00:00:00.000Z",
    counselTurnsRemaining: 10,
    insuranceDocuments: [
      {
        id: "health-1",
        fileName: "health.pdf",
        result: {
          ...POLICY_RESULT_DEFAULTS,
          status: "accepted",
          문자수: 100,
          기본정보: {
            상품명: "건강보험",
            보험분류: "제3보험",
            상품태그: [],
          },
        },
      },
    ],
  };
}

const summary = {
  totals: [],
  actual_loss_coverages: [],
  excluded_coverages: [],
  excluded_auto_policy_count: 0,
  essential_coverage_check: { items: [] },
};

describe("analysis route data flow", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  test("loads the summary without generating an overview on the policies route", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(summary)));
    vi.stubGlobal("fetch", fetchMock);

    renderWithProviders(<PolicyOverview />, { initialAnalysis: fixture() });

    await screen.findByText("표시할 보장금액을 찾지 못했어요.");
    expect(requestsFor(fetchMock, "/portfolio/summary")).toHaveLength(1);
    expect(requestsFor(fetchMock, "/portfolio/overview")).toHaveLength(0);
  });

  test("keeps policy content visible while only the summary section suspends", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>(() => undefined)),
    );

    renderWithProviders(<PolicyOverview />, { initialAnalysis: fixture() });

    expect(
      screen.getByText("내 보험을 종류별로 정리했어요"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("status", {
        name: "보장금 합계를 불러오고 있어요.",
      }),
    ).toBeInTheDocument();
  });

  test("retries a failed summary inside its local Suspense boundary", async () => {
    const user = userEvent.setup();
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce(new Response(JSON.stringify(summary)));
    vi.stubGlobal("fetch", fetchMock);

    renderWithProviders(<PolicyOverview />, { initialAnalysis: fixture() });

    expect(
      await screen.findByText("보장금 합계를 불러오지 못했어요."),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "다시 불러오기" }));

    expect(
      await screen.findByText("표시할 보장금액을 찾지 못했어요."),
    ).toBeInTheDocument();
    expect(requestsFor(fetchMock, "/portfolio/summary")).toHaveLength(2);
  });

  test("generates the overview only from the coverage analysis", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).endsWith("/portfolio/overview")) {
        return new Response(
          JSON.stringify({
            generation: "llm",
            title: "확인된 보장을 기준으로 총평을 정리했어요",
            paragraphs: ["확인된 보장 정보만 사용했어요."],
          }),
        );
      }
      return new Response(JSON.stringify(summary));
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWithProviders(<CoverageAnalysis />, { initialAnalysis: fixture() });

    await screen.findByText("핵심 보장 확인");
    await waitFor(() => {
      expect(requestsFor(fetchMock, "/portfolio/overview")).toHaveLength(1);
    });
  });

  test("reuses the cached summary when moving from policies to coverage", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).endsWith("/portfolio/overview")) {
        return new Response(
          JSON.stringify({
            generation: "llm",
            title: "총평",
            paragraphs: ["확인된 보장 정보만 사용했어요."],
          }),
        );
      }
      return new Response(JSON.stringify(summary));
    });
    vi.stubGlobal("fetch", fetchMock);

    function RouteSwitch() {
      const [route, setRoute] = useState<"policies" | "coverage">("policies");
      return (
        <>
          <button type="button" onClick={() => setRoute("coverage")}>
            보험 분석 보기
          </button>
          {route === "policies" ? <PolicyOverview /> : <CoverageAnalysis />}
        </>
      );
    }

    renderWithProviders(<RouteSwitch />, { initialAnalysis: fixture() });
    await screen.findByText("표시할 보장금액을 찾지 못했어요.");
    await user.click(screen.getByRole("button", { name: "보험 분석 보기" }));
    await screen.findByText("핵심 보장 확인");

    expect(requestsFor(fetchMock, "/portfolio/summary")).toHaveLength(1);
  });
});

function requestsFor(
  fetchMock: ReturnType<typeof vi.fn>,
  path: string,
): unknown[] {
  return fetchMock.mock.calls.filter(([input]) => String(input).endsWith(path));
}
