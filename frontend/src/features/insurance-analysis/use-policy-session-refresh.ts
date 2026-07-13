"use client";

import { useEffect } from "react";
import type { AnalyzedInsurance } from "./insurance-analysis-store";
import {
  PolicySessionExpiredError,
  refreshPolicySession,
} from "./policy-session-api";
import type { PolicySessionTokenReplacement } from "./insurance-analysis-store";

export const POLICY_SESSION_REFRESH_INTERVAL_MS = 3 * 60 * 1000;

type UsePolicySessionRefreshOptions = {
  documents: AnalyzedInsurance[];
  enabled: boolean;
  onTokensRefreshed: (
    replacements: readonly PolicySessionTokenReplacement[],
  ) => void;
  onExpired: () => void;
};

export function usePolicySessionRefresh({
  documents,
  enabled,
  onTokensRefreshed,
  onExpired,
}: UsePolicySessionRefreshOptions) {
  useEffect(() => {
    if (!enabled) return;

    let cancelled = false;
    const refresh = async () => {
      const tokens = [
        ...new Set(
          documents
            .map((document) => document.result.문서세션ID)
            .filter((token): token is string => Boolean(token)),
        ),
      ];
      if (!tokens.length) return;

      const results = await Promise.allSettled(
        tokens.map(async (token) => {
          const refreshed = await refreshPolicySession(token);
          return { currentToken: token, nextToken: refreshed.문서세션ID };
        }),
      );
      if (cancelled) return;

      const replacements = results
        .filter(
          (
            result,
          ): result is PromiseFulfilledResult<PolicySessionTokenReplacement> =>
            result.status === "fulfilled",
        )
        .map((result) => result.value);
      if (replacements.length) {
        onTokensRefreshed(replacements);
      }

      const hasExpiredSession = results.some(
        (result) =>
          result.status === "rejected" &&
          result.reason instanceof PolicySessionExpiredError,
      );
      if (hasExpiredSession) {
        onExpired();
      }
    };

    const interval = window.setInterval(() => {
      void refresh();
    }, POLICY_SESSION_REFRESH_INTERVAL_MS);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [documents, enabled, onExpired, onTokensRefreshed]);
}
