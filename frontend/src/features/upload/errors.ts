import { isExpiredPortfolioSessionApiError } from "@/shared/api/client";
import { userMessageForError } from "@/shared/api/errors";

export { isAbortError } from "@/shared/api/errors";

import { PolicyUploadError } from "./api";
import type { UploadErrorCode } from "./types";

export type SelectedFileErrorCode =
  | "INVALID_PDF"
  | "PDF_TOO_LARGE"
  | "PDF_PAGE_LIMIT_EXCEEDED"
  | "PDF_COMPLEXITY_LIMIT_EXCEEDED"
  | "PDF_PASSWORD_REQUIRED"
  | "PDF_PASSWORD_INCORRECT"
  | "PDF_TEXT_EXTRACTION_FAILED"
  | "DUPLICATE_POLICY"
  | "MISSING_INSURED_PERSON";

const FILE_SPECIFIC_UPLOAD_CODES = new Set<UploadErrorCode>([
  "INVALID_PDF",
  "PDF_TOO_LARGE",
  "PDF_PAGE_LIMIT_EXCEEDED",
  "PDF_COMPLEXITY_LIMIT_EXCEEDED",
  "PDF_PASSWORD_REQUIRED",
  "PDF_PASSWORD_INCORRECT",
  "PDF_TEXT_EXTRACTION_FAILED",
]);

export function isFileSpecificUploadError(err: unknown) {
  return (
    err instanceof PolicyUploadError && FILE_SPECIFIC_UPLOAD_CODES.has(err.code)
  );
}

export function isExpiredUploadSessionError(err: unknown) {
  return (
    (err instanceof PolicyUploadError &&
      (err.status === 403 || err.code === "INVALID_PORTFOLIO_SESSION")) ||
    isExpiredPortfolioSessionApiError(err)
  );
}

export function isPdfPasswordError(code?: string) {
  return code === "PDF_PASSWORD_REQUIRED" || code === "PDF_PASSWORD_INCORRECT";
}

export const DOCUMENT_CLEANUP_ERROR_MESSAGE =
  "업로드한 문서를 정리하지 못했어요. 다시 시도해주세요.";

export class UploadedDocumentCleanupError extends Error {
  constructor() {
    super(DOCUMENT_CLEANUP_ERROR_MESSAGE);
    this.name = "UploadedDocumentCleanupError";
  }
}

// Pick the batch-level message for a set of per-file upload failures. All
// failures reaching here are file-specific PolicyUploadErrors; unexpected
// failures are rethrown before this runs.
export function messageForFailedUploads(uploadErrors: PolicyUploadError[]) {
  const hasPasswordErrors = uploadErrors.some((uploadError) =>
    isPdfPasswordError(uploadError.code),
  );
  const onlyPasswordErrors = uploadErrors.every((uploadError) =>
    isPdfPasswordError(uploadError.code),
  );
  return onlyPasswordErrors
    ? "비밀번호가 필요한 PDF가 있어요. 표시된 파일에 비밀번호를 입력한 뒤 다시 시도해주세요."
    : hasPasswordErrors
      ? "일부 PDF는 비밀번호가 필요해요. 읽을 수 없는 PDF는 제거한 뒤 다시 시도해주세요."
      : "일부 PDF를 읽지 못했어요. 표시된 파일의 안내를 확인한 뒤 다시 시도해주세요.";
}

export function messageForSubmitFailure(err: unknown) {
  if (err instanceof UploadedDocumentCleanupError) {
    return DOCUMENT_CLEANUP_ERROR_MESSAGE;
  }
  return userMessageForError(
    err,
    "업로드에 실패했어요. 잠시 후 다시 시도해주세요.",
  );
}
