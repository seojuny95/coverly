import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  PORTFOLIO_SESSION_REFRESH_FALLBACK_MS,
  portfolioSessionRefreshDelay,
  usePortfolioSessionRefresh,
} from "./use-session-refresh";
import {
  PortfolioSessionExpiredError,
  refreshPortfolioSession,
} from "./session-api";

vi.mock("./session-api", () => {
  class PortfolioSessionExpiredError extends Error {}
  return {
    PortfolioSessionExpiredError,
    refreshPortfolioSession: vi.fn(),
  };
});

describe("usePortfolioSessionRefresh", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it("refreshes exactly one portfolio token", async () => {
    vi.useFakeTimers();
    vi.mocked(refreshPortfolioSession).mockResolvedValue({
      portfolioSessionToken: "next-portfolio-token",
      expiresAt: "2026-07-14T00:15:00+00:00",
      counselTurnsRemaining: 10,
    });
    const onRefreshed = vi.fn();

    renderHook(() =>
      usePortfolioSessionRefresh({
        session: {
          portfolioSessionToken: "current-portfolio-token",
          expiresAt: "invalid",
          counselTurnsRemaining: 10,
        },
        enabled: true,
        onRefreshed,
        onExpired: vi.fn(),
      }),
    );

    await act(async () => {
      vi.advanceTimersByTime(PORTFOLIO_SESSION_REFRESH_FALLBACK_MS);
      await Promise.resolve();
    });

    expect(refreshPortfolioSession).toHaveBeenCalledOnce();
    expect(refreshPortfolioSession).toHaveBeenCalledWith(
      "current-portfolio-token",
    );
    expect(onRefreshed).toHaveBeenCalledWith({
      portfolioSessionToken: "next-portfolio-token",
      expiresAt: "2026-07-14T00:15:00+00:00",
      counselTurnsRemaining: 10,
    });
  });

  it("reports an expired portfolio session", async () => {
    vi.useFakeTimers();
    vi.mocked(refreshPortfolioSession).mockRejectedValue(
      new PortfolioSessionExpiredError(),
    );
    const onExpired = vi.fn();

    renderHook(() =>
      usePortfolioSessionRefresh({
        session: {
          portfolioSessionToken: "expired-token",
          expiresAt: "invalid",
          counselTurnsRemaining: 10,
        },
        enabled: true,
        onRefreshed: vi.fn(),
        onExpired,
      }),
    );

    await act(async () => {
      vi.advanceTimersByTime(PORTFOLIO_SESSION_REFRESH_FALLBACK_MS);
      await Promise.resolve();
    });

    expect(onExpired).toHaveBeenCalledOnce();
  });

  it("refreshes one minute before the server expiry", () => {
    expect(
      portfolioSessionRefreshDelay(
        "2026-07-18T00:15:00.000Z",
        Date.parse("2026-07-18T00:10:00.000Z"),
      ),
    ).toBe(4 * 60 * 1000);
  });
});
