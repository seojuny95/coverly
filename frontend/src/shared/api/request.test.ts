import { afterEach, describe, expect, it, vi } from "vitest";
import { requestWithDeadline } from "./request";

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("requestWithDeadline", () => {
  it("normalizes a deadline expiry and aborts the fetch", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn(
      (_input: RequestInfo | URL, init?: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => {
            reject(new DOMException("Aborted", "AbortError"));
          });
        }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const request = requestWithDeadline(
      "https://example.test/summary",
      { method: "POST" },
      {
        timeoutMs: 500,
        timeoutMessage: "요청 시간이 초과됐어요.",
      },
    );

    const expectation = expect(request).rejects.toEqual(
      expect.objectContaining({
        name: "ApiRequestTimeoutError",
        code: "REQUEST_TIMEOUT",
        message: "API request deadline exceeded",
        userMessage: "요청 시간이 초과됐어요.",
      }),
    );
    await vi.advanceTimersByTimeAsync(500);
    await expectation;
    expect(fetchMock.mock.calls[0]?.[1]?.signal?.aborted).toBe(true);
  });

  it("keeps a caller abort distinct from a deadline expiry", async () => {
    vi.useFakeTimers();
    const caller = new AbortController();
    const abortError = new DOMException("Aborted", "AbortError");
    let rejectFetch: (error: unknown) => void = () => undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_input: RequestInfo | URL, init?: RequestInit) =>
          new Promise<Response>((_resolve, reject) => {
            rejectFetch = reject;
            init?.signal?.addEventListener("abort", () => undefined);
          }),
      ),
    );

    const request = requestWithDeadline(
      "https://example.test/summary",
      {},
      {
        signal: caller.signal,
        timeoutMs: 10_000,
        timeoutMessage: "요청 시간이 초과됐어요.",
      },
    );
    const expectation = expect(request).rejects.toBe(abortError);
    caller.abort();
    await vi.advanceTimersByTimeAsync(10_000);
    rejectFetch(abortError);

    await expectation;
  });

  it("does not start fetch when the caller already cancelled", async () => {
    const caller = new AbortController();
    caller.abort();
    const fetchMock = vi.spyOn(globalThis, "fetch");

    await expect(
      requestWithDeadline(
        "https://example.test/summary",
        {},
        {
          signal: caller.signal,
          timeoutMs: 10_000,
          timeoutMessage: "요청 시간이 초과됐어요.",
        },
      ),
    ).rejects.toMatchObject({ name: "AbortError" });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("cleans up its timeout and caller listener after a response", async () => {
    vi.useFakeTimers();
    const caller = new AbortController();
    let requestSignal: AbortSignal | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
        requestSignal = init?.signal ?? undefined;
        return Promise.resolve(new Response(null, { status: 204 }));
      }),
    );

    await expect(
      requestWithDeadline(
        "https://example.test/summary",
        {},
        {
          signal: caller.signal,
          timeoutMs: 10_000,
          timeoutMessage: "요청 시간이 초과됐어요.",
        },
      ),
    ).resolves.toMatchObject({ status: 204 });

    expect(vi.getTimerCount()).toBe(0);
    caller.abort();
    expect(requestSignal?.aborted).toBe(false);
  });
});
