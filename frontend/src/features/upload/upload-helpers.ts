import { isExpiredPortfolioSessionApiError } from "@/shared/api/client";
import { userMessageForError } from "@/shared/api/errors";

import { UploadInsuranceError, type UploadErrorCode } from "./api";

export type ApiErrorCodeOrLocalUiCode = Exclude<
  UploadErrorCode,
  "UPLOAD_NETWORK_ERROR" | "UPLOAD_FAILED"
>;

export function toFiles(files: FileList | File[]): File[] {
  return Array.from(files);
}

export function isFileSpecificUploadError(err: unknown) {
  if (!(err instanceof UploadInsuranceError)) return false;
  if (isExpiredUploadSessionError(err)) return false;
  if (err.code === "UPLOAD_NETWORK_ERROR") return false;
  if (err.status && err.status >= 500) return false;
  return true;
}

export function isExpiredUploadSessionError(err: unknown) {
  return (
    (err instanceof UploadInsuranceError &&
      (err.status === 403 || err.code === "INVALID_PORTFOLIO_SESSION")) ||
    isExpiredPortfolioSessionApiError(err)
  );
}

function isPasswordUploadError(code: UploadErrorCode) {
  return code === "PDF_PASSWORD_REQUIRED" || code === "PDF_PASSWORD_INCORRECT";
}

export const ROLLBACK_ERROR_MESSAGE =
  "업로드한 문서를 정리하지 못했어요. 다시 시도해주세요.";

export class UploadRollbackError extends Error {
  constructor() {
    super(ROLLBACK_ERROR_MESSAGE);
    this.name = "UploadRollbackError";
  }
}

export async function createFileFingerprint(file: File) {
  const buffer = await file.arrayBuffer();
  const digest = await crypto.subtle.digest("SHA-256", buffer);
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

// Pick the batch-level message for a set of per-file upload failures. All
// failures reaching here are file-specific UploadInsuranceErrors; unexpected
// failures are rethrown before this runs.
export function messageForFailedUploads(uploadErrors: UploadInsuranceError[]) {
  const hasPasswordErrors = uploadErrors.some((uploadError) =>
    isPasswordUploadError(uploadError.code),
  );
  const onlyPasswordErrors = uploadErrors.every((uploadError) =>
    isPasswordUploadError(uploadError.code),
  );
  return onlyPasswordErrors
    ? "비밀번호가 필요한 PDF가 있어요. 표시된 파일에 비밀번호를 입력한 뒤 다시 시도해주세요."
    : hasPasswordErrors
      ? "일부 PDF는 비밀번호가 필요해요. 읽을 수 없는 PDF는 제거한 뒤 다시 시도해주세요."
      : "일부 PDF를 읽지 못했어요. 표시된 파일의 안내를 확인한 뒤 다시 시도해주세요.";
}

// Map a caught submit-flow error to its user-facing message.
export function messageForSubmitFailure(err: unknown) {
  if (err instanceof UploadRollbackError) return ROLLBACK_ERROR_MESSAGE;
  return userMessageForError(
    err,
    "업로드에 실패했어요. 잠시 후 다시 시도해주세요.",
  );
}
