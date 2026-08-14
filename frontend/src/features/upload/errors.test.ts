import { describe, expect, test } from "vitest";

import { PolicyUploadError } from "./api";
import { isAbortError, isFileSpecificUploadError } from "./errors";

function uploadError(
  code: ConstructorParameters<typeof PolicyUploadError>[0]["code"],
) {
  return new PolicyUploadError({
    code,
    status: 422,
    userMessage: "테스트 오류",
  });
}

describe("upload error classification", () => {
  test.each([
    "INVALID_PDF",
    "PDF_TOO_LARGE",
    "PDF_PAGE_LIMIT_EXCEEDED",
    "PDF_COMPLEXITY_LIMIT_EXCEEDED",
    "PDF_PASSWORD_REQUIRED",
    "PDF_PASSWORD_INCORRECT",
    "PDF_TEXT_EXTRACTION_FAILED",
  ] as const)("treats %s as a file-specific error", (code) => {
    expect(isFileSpecificUploadError(uploadError(code))).toBe(true);
  });

  test.each([
    "PORTFOLIO_DOCUMENT_LIMIT_EXCEEDED",
    "POLICY_UPLOAD_IN_PROGRESS",
    "POLICY_UPLOAD_ALREADY_COMPLETED",
    "POLICY_UPLOAD_CANCELLED",
    "REQUEST_VALIDATION_ERROR",
  ] as const)("keeps %s at the form level", (code) => {
    expect(isFileSpecificUploadError(uploadError(code))).toBe(false);
  });

  test("recognizes intentional request cancellation", () => {
    expect(isAbortError(new DOMException("Aborted", "AbortError"))).toBe(true);
    expect(isAbortError(new Error("network failed"))).toBe(false);
  });
});
