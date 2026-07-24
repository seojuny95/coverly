import type { paths } from "./generated";
import type {
  ApiErrorCode,
  ApiErrorDetail,
  ApiErrorResponse,
} from "./contracts";
import { AppRequestError } from "./errors";
import { isApiErrorCode } from "./generated-runtime";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export function apiUrl(path: keyof paths): string {
  return `${API_BASE_URL}${path}`;
}

export class ApiResponseError extends AppRequestError {
  readonly code?: ApiErrorCode;
  readonly requestId?: string;
  readonly retryAfterMs?: number;
  readonly status: number;

  constructor({
    code,
    requestId,
    retryAfterMs,
    status,
    userMessage,
  }: {
    code?: ApiErrorCode;
    requestId?: string;
    retryAfterMs?: number;
    status: number;
    userMessage: string;
  }) {
    super({
      developerMessage: `API request failed (status=${status}, code=${code ?? "UNKNOWN"})`,
      name: "ApiResponseError",
      userMessage,
    });
    this.code = code;
    this.requestId = requestId;
    this.retryAfterMs = retryAfterMs;
    this.status = status;
  }
}

export function hasApiErrorCode(
  error: unknown,
  code: ApiErrorCode,
): error is ApiResponseError {
  return error instanceof ApiResponseError && error.code === code;
}

export function isExpiredPortfolioSessionApiError(
  error: unknown,
): error is ApiResponseError {
  return (
    error instanceof ApiResponseError &&
    (error.status === 403 ||
      hasApiErrorCode(error, "INVALID_PORTFOLIO_SESSION"))
  );
}

export async function apiResponseError(
  response: Response,
  fallbackMessage: string,
): Promise<ApiResponseError> {
  const detail = await readApiError(response);
  return new ApiResponseError({
    code: detail?.code,
    requestId:
      detail?.request_id ?? response.headers.get("x-request-id") ?? undefined,
    retryAfterMs: retryAfterMilliseconds(response.headers.get("retry-after")),
    status: response.status,
    userMessage: detail?.message ?? fallbackMessage,
  });
}

function retryAfterMilliseconds(value: string | null): number | undefined {
  if (!value) return undefined;

  const seconds = Number(value);
  if (Number.isFinite(seconds) && seconds >= 0) return seconds * 1000;

  const retryAt = Date.parse(value);
  if (!Number.isFinite(retryAt)) return undefined;
  return Math.max(0, retryAt - Date.now());
}

async function readApiError(
  response: Response,
): Promise<ApiErrorDetail | null> {
  return (await readApiErrorPayload(response)).detail;
}

export async function readApiErrorPayload(response: Response): Promise<{
  detail: ApiErrorDetail | null;
  isJson: boolean;
}> {
  try {
    const payload: unknown = await response.json();
    if (!isApiErrorResponse(payload)) {
      return { detail: null, isJson: true };
    }

    return {
      detail: payload.error,
      isJson: true,
    };
  } catch {
    return { detail: null, isJson: false };
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isApiErrorResponse(value: unknown): value is ApiErrorResponse {
  if (!isRecord(value) || !isRecord(value.error)) return false;
  return (
    isApiErrorCode(value.error.code) &&
    typeof value.error.message === "string" &&
    typeof value.error.request_id === "string"
  );
}
