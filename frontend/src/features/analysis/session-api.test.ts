import { afterEach, describe, expect, it, vi } from "vitest";
import {
  createPortfolioSession,
  deletePortfolioSessionDocuments,
  deletePortfolioSession,
  refreshPortfolioSession,
} from "./session-api";
import { waitForBackendReady } from "@/shared/api/readiness";

vi.mock("@/shared/api/readiness", () => ({
  waitForBackendReady: vi.fn(),
}));

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.clearAllMocks();
});

describe("portfolio session API", () => {
  it("creates one server-side portfolio session", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          portfolioSessionToken: "portfolio-token",
          expiresAt: "2026-07-18T10:00:00Z",
        }),
        { status: 200 },
      ),
    );

    await expect(createPortfolioSession()).resolves.toMatchObject({
      portfolioSessionToken: "portfolio-token",
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/portfolio/sessions",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("accepts a caller cancellation signal for session requests", async () => {
    const caller = new AbortController();
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          portfolioSessionToken: "portfolio-token",
          expiresAt: "2026-07-18T10:00:00Z",
        }),
        { status: 200 },
      ),
    );

    await createPortfolioSession(caller.signal);

    const signal = fetchMock.mock.calls[0]?.[1]?.signal;
    expect(signal).toBeInstanceOf(AbortSignal);
    expect(signal).not.toBe(caller.signal);
  });

  it("keeps timeout diagnostics out of the user-facing message", async () => {
    vi.useFakeTimers();
    vi.spyOn(globalThis, "fetch").mockImplementation(
      (_input, init) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => {
            reject(new DOMException("Aborted", "AbortError"));
          });
        }),
    );

    const request = createPortfolioSession();
    const expectation = expect(request).rejects.toMatchObject({
      name: "ApiRequestTimeoutError",
      message: "API request deadline exceeded",
      userMessage:
        "분석 세션을 확인하는 시간이 길어지고 있어요. 잠시 후 다시 시도해주세요.",
    });

    await vi.advanceTimersByTimeAsync(15 * 1000);
    await expectation;
  });

  it("refreshes and deletes the same bearer token", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            portfolioSessionToken: "next-token",
            expiresAt: "2026-07-18T10:00:00Z",
          }),
          { status: 200 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ status: "deleted" }), { status: 200 }),
      );

    await refreshPortfolioSession("current-token");
    await deletePortfolioSession("next-token");

    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({
      body: JSON.stringify({ portfolioSessionToken: "current-token" }),
    });
    expect(fetchMock.mock.calls[1]?.[1]).toMatchObject({
      body: JSON.stringify({ portfolioSessionToken: "next-token" }),
    });
  });

  it("waits for a sleeping backend before retrying a safe refresh", async () => {
    vi.mocked(waitForBackendReady).mockResolvedValue(undefined);
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockRejectedValueOnce(new TypeError("network"))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            portfolioSessionToken: "next-token",
            expiresAt: "2026-07-18T10:00:00Z",
          }),
          { status: 200 },
        ),
      );

    await expect(
      refreshPortfolioSession("current-token"),
    ).resolves.toMatchObject({
      portfolioSessionToken: "next-token",
    });

    expect(waitForBackendReady).toHaveBeenCalledOnce();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("deletes selected documents from a valid portfolio session", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        new Response(JSON.stringify({ status: "deleted" }), { status: 200 }),
      );

    await deletePortfolioSessionDocuments("portfolio-token", [
      "document-1",
      "document-2",
    ]);

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/portfolio/sessions/documents/delete",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          portfolioSessionToken: "portfolio-token",
          documentIds: ["document-1", "document-2"],
        }),
      }),
    );
  });
});
