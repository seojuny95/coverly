import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  PORTFOLIO_SESSION_REFRESH_FALLBACK_MS,
  PORTFOLIO_SESSION_REFRESH_RETRY_MS,
  portfolioSessionNeedsRefresh,
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
      expect.any(AbortSignal),
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

  it("retries refresh after a transient failure", async () => {
    vi.useFakeTimers();
    vi.mocked(refreshPortfolioSession)
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce({
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
    expect(onRefreshed).not.toHaveBeenCalled();

    await act(async () => {
      vi.advanceTimersByTime(PORTFOLIO_SESSION_REFRESH_RETRY_MS);
      await Promise.resolve();
    });

    expect(refreshPortfolioSession).toHaveBeenCalledTimes(2);
    expect(onRefreshed).toHaveBeenCalledWith({
      portfolioSessionToken: "next-portfolio-token",
      expiresAt: "2026-07-14T00:15:00+00:00",
      counselTurnsRemaining: 10,
    });
  });

  it("expires the session instead of retrying forever after the server expiry passes", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-07-18T00:13:59.000Z"));
    vi.mocked(refreshPortfolioSession).mockRejectedValue(new Error("offline"));
    const onExpired = vi.fn();

    renderHook(() =>
      usePortfolioSessionRefresh({
        session: {
          portfolioSessionToken: "current-portfolio-token",
          expiresAt: "2026-07-18T00:15:00.000Z",
          counselTurnsRemaining: 10,
        },
        enabled: true,
        onRefreshed: vi.fn(),
        onExpired,
      }),
    );

    await act(async () => {
      vi.advanceTimersByTime(1000);
      await Promise.resolve();
    });
    expect(refreshPortfolioSession).toHaveBeenCalledOnce();
    expect(onExpired).not.toHaveBeenCalled();

    await act(async () => {
      vi.advanceTimersByTime(PORTFOLIO_SESSION_REFRESH_RETRY_MS);
      await Promise.resolve();
    });
    expect(refreshPortfolioSession).toHaveBeenCalledTimes(2);
    expect(onExpired).not.toHaveBeenCalled();

    await act(async () => {
      vi.advanceTimersByTime(PORTFOLIO_SESSION_REFRESH_RETRY_MS);
      await Promise.resolve();
    });

    expect(refreshPortfolioSession).toHaveBeenCalledTimes(2);
    expect(onExpired).toHaveBeenCalledOnce();
  });

  it("refreshes five minutes before the server expiry", () => {
    expect(
      portfolioSessionRefreshDelay(
        "2026-07-18T00:15:00.000Z",
        Date.parse("2026-07-18T00:05:00.000Z"),
      ),
    ).toBe(5 * 60 * 1000);
  });

  it("does not refresh on tab focus while the session has enough time", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-07-18T00:00:00.000Z"));
    vi.mocked(refreshPortfolioSession).mockResolvedValue({
      portfolioSessionToken: "next-portfolio-token",
      expiresAt: "2026-07-18T00:30:00.000Z",
      counselTurnsRemaining: 10,
    });

    renderHook(() =>
      usePortfolioSessionRefresh({
        session: {
          portfolioSessionToken: "current-portfolio-token",
          expiresAt: "2026-07-18T00:15:00.000Z",
          counselTurnsRemaining: 10,
        },
        enabled: true,
        onRefreshed: vi.fn(),
        onExpired: vi.fn(),
      }),
    );

    window.dispatchEvent(new Event("focus"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(refreshPortfolioSession).not.toHaveBeenCalled();
  });

  it("refreshes when the user returns near session expiry", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-07-18T00:11:00.000Z"));
    vi.mocked(refreshPortfolioSession).mockResolvedValue({
      portfolioSessionToken: "next-portfolio-token",
      expiresAt: "2026-07-18T00:30:00.000Z",
      counselTurnsRemaining: 10,
    });

    renderHook(() =>
      usePortfolioSessionRefresh({
        session: {
          portfolioSessionToken: "current-portfolio-token",
          expiresAt: "2026-07-18T00:15:00.000Z",
          counselTurnsRemaining: 10,
        },
        enabled: true,
        onRefreshed: vi.fn(),
        onExpired: vi.fn(),
      }),
    );

    window.dispatchEvent(new Event("focus"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(refreshPortfolioSession).toHaveBeenCalledWith(
      "current-portfolio-token",
      expect.any(AbortSignal),
    );
  });

  it("classifies invalid and near-expiry timestamps for recovery", () => {
    const now = Date.parse("2026-07-18T00:00:00.000Z");

    expect(portfolioSessionNeedsRefresh("invalid", now)).toBe(true);
    expect(portfolioSessionNeedsRefresh("2026-07-18T00:04:59.000Z", now)).toBe(
      true,
    );
    expect(portfolioSessionNeedsRefresh("2026-07-18T00:05:01.000Z", now)).toBe(
      false,
    );
  });
});
