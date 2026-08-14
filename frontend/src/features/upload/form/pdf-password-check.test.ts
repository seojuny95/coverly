import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

const destroy = vi.fn().mockResolvedValue(undefined);

vi.mock("pdfjs-dist", () => ({
  GlobalWorkerOptions: {},
  getDocument: () => ({
    promise: new Promise(() => {}),
    destroy,
  }),
  PasswordResponses: { NEED_PASSWORD: 1 },
}));

import {
  isPdfPasswordProtected,
  PASSWORD_CHECK_TIMEOUT_MS,
} from "./pdf-password-check";

describe("isPdfPasswordProtected", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    destroy.mockClear();
  });
  afterEach(() => vi.useRealTimers());

  test("fails open to false when the check hangs past the timeout", async () => {
    const file = new File(["%PDF-1.7"], "insurance.pdf", {
      type: "application/pdf",
    });

    const resultPromise = isPdfPasswordProtected(file);
    await vi.advanceTimersByTimeAsync(PASSWORD_CHECK_TIMEOUT_MS);

    await expect(resultPromise).resolves.toBe(false);
  });

  test("destroys the stalled loading task when the timeout fires, so the worker doesn't leak", async () => {
    const file = new File(["%PDF-1.7"], "insurance.pdf", {
      type: "application/pdf",
    });

    const resultPromise = isPdfPasswordProtected(file);
    await vi.advanceTimersByTimeAsync(PASSWORD_CHECK_TIMEOUT_MS);
    await resultPromise;

    expect(destroy).toHaveBeenCalledOnce();
  });

  test("still fails open when destroying the timed-out loading task itself throws", async () => {
    destroy.mockRejectedValueOnce(new Error("worker already gone"));
    const file = new File(["%PDF-1.7"], "insurance.pdf", {
      type: "application/pdf",
    });

    const resultPromise = isPdfPasswordProtected(file);
    await vi.advanceTimersByTimeAsync(PASSWORD_CHECK_TIMEOUT_MS);

    await expect(resultPromise).resolves.toBe(false);
  });
});
