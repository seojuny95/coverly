import { afterEach, describe, expect, it, vi } from "vitest";
import {
  PolicySessionExpiredError,
  refreshPolicySession,
} from "./policy-session-api";

describe("policy session API", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("refreshes a document session token", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            문서세션ID: "new-token",
            expiresAt: "2026-07-14T00:15:00+00:00",
          }),
        ),
      ),
    );

    await expect(refreshPolicySession("old-token")).resolves.toEqual({
      문서세션ID: "new-token",
      expiresAt: "2026-07-14T00:15:00+00:00",
    });
    expect(fetch).toHaveBeenCalledWith(
      "http://localhost:8000/policies/sessions/refresh",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ 문서세션ID: "old-token" }),
      }),
    );
  });

  it("maps invalid sessions to an expiration error", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(
            JSON.stringify({ error: { code: "INVALID_POLICY_SESSION" } }),
            { status: 403 },
          ),
        ),
    );

    await expect(refreshPolicySession("old-token")).rejects.toBeInstanceOf(
      PolicySessionExpiredError,
    );
  });
});
