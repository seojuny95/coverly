import { afterEach, describe, expect, it, vi } from "vitest";
import {
  BACKEND_READINESS_ERROR_MESSAGE,
  BackendReadinessError,
  waitForBackendReady,
} from "./readiness";

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("waitForBackendReady", () => {
  it("accepts only the Coverly health response", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response("<html>Render is starting</html>", {
          status: 200,
          headers: { "Content-Type": "text/html" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ status: "ok" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );

    await waitForBackendReady({ retryDelayMs: 0 });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock).toHaveBeenLastCalledWith(
      "http://localhost:8000/health",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("retries transient connection failures until the backend is ready", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ status: "ok" }), { status: 200 }),
      );

    await waitForBackendReady({ retryDelayMs: 0 });

    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("honors Retry-After without polling a rate-limited backend", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response(null, {
          status: 429,
          headers: { "Retry-After": "3" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ status: "ok" }), { status: 200 }),
      );

    const readiness = waitForBackendReady({ timeoutMs: 5000 });
    await vi.advanceTimersByTimeAsync(2999);
    expect(fetchMock).toHaveBeenCalledOnce();

    await vi.advanceTimersByTimeAsync(1);
    await readiness;
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("fails immediately when the health endpoint is permanently unavailable", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response(null, { status: 404 }));

    await expect(
      waitForBackendReady({ retryDelayMs: 0 }),
    ).rejects.toMatchObject({ name: "BackendReadinessError" });
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("returns a user-facing error after the readiness deadline", async () => {
    vi.useFakeTimers();
    vi.spyOn(globalThis, "fetch").mockRejectedValue(
      new TypeError("Failed to fetch"),
    );

    const readiness = waitForBackendReady({
      timeoutMs: 100,
      attemptTimeoutMs: 50,
      retryDelayMs: 10,
    });
    const expectation = expect(readiness).rejects.toEqual(
      new BackendReadinessError(),
    );

    await vi.advanceTimersByTimeAsync(100);
    await expectation;
    expect(BACKEND_READINESS_ERROR_MESSAGE).toContain(
      "분석 서버를 준비하지 못했어요",
    );
  });

  it("propagates caller cancellation without converting it to an outage", async () => {
    vi.useFakeTimers();
    const caller = new AbortController();
    vi.spyOn(globalThis, "fetch").mockImplementation(
      (_input, init) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => {
            reject(new DOMException("Aborted", "AbortError"));
          });
        }),
    );

    const readiness = waitForBackendReady({
      signal: caller.signal,
      timeoutMs: 1000,
    });
    const expectation = expect(readiness).rejects.toMatchObject({
      name: "AbortError",
    });
    caller.abort();

    await expectation;
  });
});
