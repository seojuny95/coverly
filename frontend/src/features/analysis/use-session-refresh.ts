"use client";

import { useEffect } from "react";
import {
  PortfolioSessionExpiredError,
  refreshPortfolioSession,
  type PortfolioSessionResult,
} from "./session-api";
import { reportClientOperationFailure } from "@/shared/api/errors";

export const PORTFOLIO_SESSION_REFRESH_FALLBACK_MS = 3 * 60 * 1000;
export const PORTFOLIO_SESSION_REFRESH_RETRY_MS = 30 * 1000;
const REFRESH_SAFETY_WINDOW_MS = 5 * 60 * 1000;
const MIN_REFRESH_DELAY_MS = 1000;
const MAX_REFRESH_DELAY_MS = 24 * 60 * 60 * 1000;

type UsePortfolioSessionRefreshOptions = {
  session?: PortfolioSessionResult;
  enabled: boolean;
  onRefreshed: (session: PortfolioSessionResult) => void;
  onExpired: () => void;
};

export function portfolioSessionRefreshDelay(
  expiresAt: string,
  now = Date.now(),
) {
  const expiresAtMs = Date.parse(expiresAt);
  if (!Number.isFinite(expiresAtMs)) {
    return PORTFOLIO_SESSION_REFRESH_FALLBACK_MS;
  }
  return Math.min(
    MAX_REFRESH_DELAY_MS,
    Math.max(
      MIN_REFRESH_DELAY_MS,
      expiresAtMs - now - REFRESH_SAFETY_WINDOW_MS,
    ),
  );
}

function portfolioSessionHasExpired(expiresAt: string, now = Date.now()) {
  const expiresAtMs = Date.parse(expiresAt);
  return Number.isFinite(expiresAtMs) && expiresAtMs <= now;
}

export function portfolioSessionNeedsRefresh(
  expiresAt: string,
  now = Date.now(),
) {
  const expiresAtMs = Date.parse(expiresAt);
  return (
    !Number.isFinite(expiresAtMs) ||
    expiresAtMs - now <= REFRESH_SAFETY_WINDOW_MS
  );
}

export function usePortfolioSessionRefresh({
  session,
  enabled,
  onRefreshed,
  onExpired,
}: UsePortfolioSessionRefreshOptions) {
  useEffect(() => {
    if (!enabled || !session) return;

    let cancelled = false;
    let timeout: number | undefined;
    let refreshInFlight = false;
    let expiredReported = false;
    const controller = new AbortController();
    const scheduleRefresh = (delay: number) => {
      if (timeout !== undefined) window.clearTimeout(timeout);
      timeout = window.setTimeout(() => {
        void refresh();
      }, delay);
    };
    const reportExpired = () => {
      if (cancelled || expiredReported) return;
      expiredReported = true;
      onExpired();
    };
    const refresh = async () => {
      if (refreshInFlight) return;
      if (portfolioSessionHasExpired(session.expiresAt)) {
        reportExpired();
        return;
      }
      refreshInFlight = true;
      try {
        const refreshed = await refreshPortfolioSession(
          session.portfolioSessionToken,
          controller.signal,
        );
        if (!cancelled) {
          onRefreshed(refreshed);
        }
      } catch (error) {
        if (
          !cancelled &&
          (error instanceof PortfolioSessionExpiredError ||
            portfolioSessionHasExpired(session.expiresAt))
        ) {
          reportExpired();
          return;
        }
        if (!cancelled) {
          reportClientOperationFailure("portfolio_session_refresh", error);
          scheduleRefresh(PORTFOLIO_SESSION_REFRESH_RETRY_MS);
        }
      } finally {
        refreshInFlight = false;
      }
    };
    const refreshOnResume = () => {
      if (document.visibilityState !== "visible") return;
      if (portfolioSessionHasExpired(session.expiresAt)) {
        reportExpired();
        return;
      }
      if (!portfolioSessionNeedsRefresh(session.expiresAt)) return;
      scheduleRefresh(0);
    };

    scheduleRefresh(portfolioSessionRefreshDelay(session.expiresAt));
    window.addEventListener("focus", refreshOnResume);
    document.addEventListener("visibilitychange", refreshOnResume);

    return () => {
      cancelled = true;
      controller.abort();
      if (timeout !== undefined) window.clearTimeout(timeout);
      window.removeEventListener("focus", refreshOnResume);
      document.removeEventListener("visibilitychange", refreshOnResume);
    };
  }, [enabled, onExpired, onRefreshed, session]);
}
