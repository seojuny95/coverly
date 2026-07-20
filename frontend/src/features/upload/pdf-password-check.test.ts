import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

vi.mock("pdfjs-dist", () => ({
  GlobalWorkerOptions: {},
  getDocument: () => ({
    promise: new Promise(() => {}),
    destroy: vi.fn(),
  }),
  PasswordResponses: { NEED_PASSWORD: 1 },
}));

import {
  isPdfPasswordProtected,
  PASSWORD_CHECK_TIMEOUT_MS,
} from "./pdf-password-check";

describe("isPdfPasswordProtected", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  test("fails open to false when the check hangs past the timeout", async () => {
    const file = new File(["%PDF-1.7"], "insurance.pdf", {
      type: "application/pdf",
    });

    const resultPromise = isPdfPasswordProtected(file);
    await vi.advanceTimersByTimeAsync(PASSWORD_CHECK_TIMEOUT_MS);

    await expect(resultPromise).resolves.toBe(false);
  });
});
