"use client";

import { useEffect } from "react";
import {
  PortfolioSessionExpiredError,
  refreshPortfolioSession,
  type PortfolioSessionResult,
} from "./portfolio-session-api";

export const PORTFOLIO_SESSION_REFRESH_FALLBACK_MS = 3 * 60 * 1000;
const REFRESH_SAFETY_WINDOW_MS = 60 * 1000;
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

export function usePortfolioSessionRefresh({
  session,
  enabled,
  onRefreshed,
  onExpired,
}: UsePortfolioSessionRefreshOptions) {
  useEffect(() => {
    if (!enabled || !session) return;

    let cancelled = false;
    const refresh = async () => {
      try {
        const refreshed = await refreshPortfolioSession(
          session.portfolioSessionToken,
        );
        if (!cancelled) {
          onRefreshed(refreshed);
        }
      } catch (error) {
        if (!cancelled && error instanceof PortfolioSessionExpiredError) {
          onExpired();
        }
      }
    };

    const timeout = window.setTimeout(() => {
      void refresh();
    }, portfolioSessionRefreshDelay(session.expiresAt));

    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
    };
  }, [enabled, onExpired, onRefreshed, session]);
}
