import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { UploadedDocumentCleanupError } from "../errors";
import { useServerDocumentCleanup } from "./use-document-cleanup";

describe("useServerDocumentCleanup", () => {
  it("deduplicates document ids when rolling back uploaded documents", async () => {
    const deleteSessionDocuments = vi.fn().mockResolvedValue(undefined);
    const { result } = renderHook(() =>
      useServerDocumentCleanup(deleteSessionDocuments),
    );

    await act(async () => {
      await result.current.rollbackSessionDocuments("session-token", [
        "document-1",
        "document-1",
        "document-2",
      ]);
    });

    expect(deleteSessionDocuments).toHaveBeenCalledWith("session-token", [
      "document-1",
      "document-2",
    ]);
  });

  it("keeps a failed rollback pending and retries it before the next upload", async () => {
    const deleteSessionDocuments = vi
      .fn()
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce(undefined);
    const { result } = renderHook(() =>
      useServerDocumentCleanup(deleteSessionDocuments),
    );

    await expect(
      result.current.rollbackSessionDocuments("session-token", ["document-1"]),
    ).rejects.toBeInstanceOf(UploadedDocumentCleanupError);

    await expect(result.current.resolvePendingCleanup()).resolves.toBe(true);
    expect(deleteSessionDocuments).toHaveBeenLastCalledWith("session-token", [
      "document-1",
    ]);
  });

  it("reports when pending cleanup still cannot be resolved", async () => {
    const deleteSessionDocuments = vi
      .fn()
      .mockRejectedValue(new Error("offline"));
    const { result } = renderHook(() =>
      useServerDocumentCleanup(deleteSessionDocuments),
    );

    await expect(
      result.current.rollbackSessionDocuments("session-token", ["document-1"]),
    ).rejects.toBeInstanceOf(UploadedDocumentCleanupError);

    await expect(result.current.resolvePendingCleanup()).resolves.toBe(false);
  });
});
