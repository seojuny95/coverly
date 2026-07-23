import { isExpiredPortfolioSessionApiError } from "@/shared/api/client";

export function isExpiredSessionError(error: unknown) {
  return isExpiredPortfolioSessionApiError(error);
}
