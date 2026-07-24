import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiResponseError } from "./client";
import { retryOperation } from "./retry";

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("retryOperation", () => {
  it("retries a transient response and honors Retry-After", async () => {
    vi.useFakeTimers();
    const operation = vi
      .fn<() => Promise<string>>()
      .mockRejectedValueOnce(
        new ApiResponseError({
          status: 503,
          retryAfterMs: 2000,
          userMessage: "잠시 후 다시 시도해주세요.",
        }),
      )
      .mockResolvedValueOnce("ok");

    const result = retryOperation(operation, { maxAttempts: 2 });
    await vi.advanceTimersByTimeAsync(1999);
    expect(operation).toHaveBeenCalledOnce();
    await vi.advanceTimersByTimeAsync(1);

    await expect(result).resolves.toBe("ok");
    expect(operation).toHaveBeenCalledTimes(2);
  });

  it("does not retry a permanent client error", async () => {
    const operation = vi.fn().mockRejectedValue(
      new ApiResponseError({
        status: 422,
        userMessage: "입력 내용을 확인해주세요.",
      }),
    );

    await expect(
      retryOperation(operation, { maxAttempts: 3 }),
    ).rejects.toMatchObject({ status: 422 });
    expect(operation).toHaveBeenCalledOnce();
  });

  it("runs recovery before a retry", async () => {
    const recovery = vi.fn().mockResolvedValue(undefined);
    const operation = vi
      .fn<() => Promise<string>>()
      .mockRejectedValueOnce(new TypeError("network"))
      .mockResolvedValueOnce("ok");

    await expect(
      retryOperation(operation, {
        maxAttempts: 2,
        beforeRetry: recovery,
      }),
    ).resolves.toBe("ok");

    expect(recovery).toHaveBeenCalledWith(expect.any(TypeError), 2);
  });

  it("stops before sending when already cancelled", async () => {
    const controller = new AbortController();
    controller.abort();
    const operation = vi.fn();

    await expect(
      retryOperation(operation, {
        maxAttempts: 2,
        signal: controller.signal,
      }),
    ).rejects.toMatchObject({ name: "AbortError" });
    expect(operation).not.toHaveBeenCalled();
  });
});
