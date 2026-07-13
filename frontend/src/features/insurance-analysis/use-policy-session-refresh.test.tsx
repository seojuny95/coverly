import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AnalyzedInsurance } from "./insurance-analysis-store";
import {
  POLICY_SESSION_REFRESH_INTERVAL_MS,
  usePolicySessionRefresh,
} from "./use-policy-session-refresh";
import {
  PolicySessionExpiredError,
  refreshPolicySession,
} from "./policy-session-api";

vi.mock("./policy-session-api", () => {
  class PolicySessionExpiredError extends Error {
    constructor() {
      super("Policy session expired");
      this.name = "PolicySessionExpiredError";
    }
  }
  return {
    PolicySessionExpiredError,
    refreshPolicySession: vi.fn(),
  };
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((innerResolve, innerReject) => {
    resolve = innerResolve;
    reject = innerReject;
  });
  return { promise, resolve, reject };
}

function documentWithToken(id: string, token: string): AnalyzedInsurance {
  return {
    id,
    fileName: `${id}.pdf`,
    result: {
      status: "accepted",
      문자수: 1,
      문서세션ID: token,
    },
  };
}

describe("usePolicySessionRefresh", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it("waits for every policy token before applying one batched update", async () => {
    vi.useFakeTimers();
    const first = deferred<{ 문서세션ID: string; expiresAt: string }>();
    const second = deferred<{ 문서세션ID: string; expiresAt: string }>();
    vi.mocked(refreshPolicySession).mockImplementation((token) => {
      if (token === "old-token-a") return first.promise;
      if (token === "old-token-b") return second.promise;
      throw new Error(`Unexpected token: ${token}`);
    });
    const onTokensRefreshed = vi.fn();

    renderHook(() =>
      usePolicySessionRefresh({
        documents: [
          documentWithToken("a", "old-token-a"),
          documentWithToken("b", "old-token-b"),
        ],
        enabled: true,
        onTokensRefreshed,
        onExpired: vi.fn(),
      }),
    );

    act(() => {
      vi.advanceTimersByTime(POLICY_SESSION_REFRESH_INTERVAL_MS);
    });

    expect(refreshPolicySession).toHaveBeenCalledWith("old-token-a");
    expect(refreshPolicySession).toHaveBeenCalledWith("old-token-b");

    await act(async () => {
      first.resolve({
        문서세션ID: "new-token-a",
        expiresAt: "2026-07-14T00:15:00+00:00",
      });
      await Promise.resolve();
    });
    expect(onTokensRefreshed).not.toHaveBeenCalled();

    await act(async () => {
      second.resolve({
        문서세션ID: "new-token-b",
        expiresAt: "2026-07-14T00:15:00+00:00",
      });
      await Promise.resolve();
    });

    expect(onTokensRefreshed).toHaveBeenCalledTimes(1);
    expect(onTokensRefreshed).toHaveBeenCalledWith([
      { currentToken: "old-token-a", nextToken: "new-token-a" },
      { currentToken: "old-token-b", nextToken: "new-token-b" },
    ]);
  });

  it("applies successful token refreshes before reporting an expired session", async () => {
    vi.useFakeTimers();
    vi.mocked(refreshPolicySession).mockImplementation((token) => {
      if (token === "old-token-a") {
        return Promise.resolve({
          문서세션ID: "new-token-a",
          expiresAt: "2026-07-14T00:15:00+00:00",
        });
      }
      if (token === "old-token-b") {
        return Promise.reject(new PolicySessionExpiredError());
      }
      throw new Error(`Unexpected token: ${token}`);
    });
    const onTokensRefreshed = vi.fn();
    const onExpired = vi.fn();

    renderHook(() =>
      usePolicySessionRefresh({
        documents: [
          documentWithToken("a", "old-token-a"),
          documentWithToken("b", "old-token-b"),
        ],
        enabled: true,
        onTokensRefreshed,
        onExpired,
      }),
    );

    await act(async () => {
      vi.advanceTimersByTime(POLICY_SESSION_REFRESH_INTERVAL_MS);
      await Promise.resolve();
    });

    expect(onTokensRefreshed).toHaveBeenCalledWith([
      { currentToken: "old-token-a", nextToken: "new-token-a" },
    ]);
    expect(onExpired).toHaveBeenCalledTimes(1);
  });
});
