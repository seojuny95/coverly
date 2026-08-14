import { describe, expect, test, vi } from "vitest";

import { submitPolicyUpload } from "./submit";

describe("submitPolicyUpload", () => {
  test("returns cancelled when server preparation is intentionally aborted", async () => {
    const controller = new AbortController();
    const result = await submitPolicyUpload({
      input: {
        selectedFiles: [
          {
            id: "selected-file",
            file: new File(["%PDF-1.7"], "insurance.pdf", {
              type: "application/pdf",
            }),
            status: "idle",
          },
        ],
        currentAnalysis: null,
        existingDocuments: [],
        signal: controller.signal,
      },
      services: {
        resolvePendingCleanup: vi.fn().mockResolvedValue(true),
        prepareServer: vi.fn(async () => {
          controller.abort();
          throw new DOMException("Aborted", "AbortError");
        }),
        createSession: vi.fn(),
        uploadPolicyDocument: vi.fn(),
        rollbackSessionDocuments: vi.fn().mockResolvedValue([]),
      },
      onProgress: vi.fn(),
    });

    expect(result).toEqual({ kind: "cancelled" });
  });
});
