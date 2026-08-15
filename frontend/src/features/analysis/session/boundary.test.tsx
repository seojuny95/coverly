import { act, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";

import { AnalysisSessionBoundary } from "./boundary";
import { SessionExpiredNotice } from "./expired-notice";
import type { InsuranceAnalysis } from "./store";
import { PORTFOLIO_SESSION_REFRESH_FALLBACK_MS } from "./use-session-refresh";
import { POLICY_RESULT_DEFAULTS } from "@/test/api-fixtures";
import { renderWithProviders } from "@/test/render-with-providers";

function analysisWithSession(token: string): InsuranceAnalysis {
  return {
    generatedAt: "2026-07-09T07:30:00.000Z",
    portfolioKind: "uploaded" as const,
    portfolioSessionToken: token,
    portfolioSessionExpiresAt: "invalid",
    counselTurnsRemaining: 10,
    insuranceDocuments: [
      {
        id: "insurance-1",
        fileName: "health.pdf",
        result: { ...POLICY_RESULT_DEFAULTS, 문자수: 100 },
      },
    ],
  };
}

function SessionTestContent() {
  return (
    <AnalysisSessionBoundary>
      <SessionExpiredNotice />
      <span>분석 내용</span>
    </AnalysisSessionBoundary>
  );
}

describe("AnalysisSessionBoundary", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  test("shows the empty state when no analysis exists", () => {
    renderWithProviders(<SessionTestContent />);

    expect(screen.getByText("분석할 보험증권이 없어요")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "보험증권 올리기" }),
    ).toHaveAttribute("href", "/upload");
  });

  test("refreshes the portfolio session while analysis routes are mounted", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          portfolioSessionToken: "new-session-token",
          portfolioSessionExpiresAt: "invalid",
          counselTurnsRemaining: 10,
          expiresAt: "2026-07-14T00:15:00+00:00",
        }),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    renderWithProviders(<SessionTestContent />, {
      initialAnalysis: analysisWithSession("old-session-token"),
    });

    act(() => {
      vi.advanceTimersByTime(PORTFOLIO_SESSION_REFRESH_FALLBACK_MS);
    });
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/portfolio/sessions/refresh",
      expect.objectContaining({
        body: JSON.stringify({ portfolioSessionToken: "old-session-token" }),
      }),
    );
  });

  test("shows a notice when the session refresh is rejected", async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(
            JSON.stringify({ error: { code: "INVALID_PORTFOLIO_SESSION" } }),
            { status: 403 },
          ),
        ),
    );

    renderWithProviders(<SessionTestContent />, {
      initialAnalysis: analysisWithSession("expired-session-token"),
    });

    act(() => {
      vi.advanceTimersByTime(PORTFOLIO_SESSION_REFRESH_FALLBACK_MS);
    });
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(screen.getByText("분석 세션이 만료됐어요")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "보험증권 다시 올리기" }),
    ).toHaveAttribute("href", "/upload");
  });
});
