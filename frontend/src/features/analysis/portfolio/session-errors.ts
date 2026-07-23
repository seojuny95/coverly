import { ApiResponseError } from "@/shared/api/client";

export function isExpiredSessionError(error: unknown) {
  return error instanceof ApiResponseError && error.status === 403;
}
