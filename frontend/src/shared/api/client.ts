import type { paths } from "./generated";
import type { ApiErrorDetail, ApiErrorResponse } from "./contracts";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export function apiUrl(path: keyof paths): string {
  return `${API_BASE_URL}${path}`;
}

export class ApiResponseError extends Error {
  readonly code?: string;
  readonly requestId?: string;
  readonly status: number;

  constructor({
    code,
    message,
    requestId,
    status,
  }: {
    code?: string;
    message: string;
    requestId?: string;
    status: number;
  }) {
    super(message);
    this.name = "ApiResponseError";
    this.code = code;
    this.requestId = requestId;
    this.status = status;
  }
}

export async function apiResponseError(
  response: Response,
  fallbackMessage: string,
): Promise<ApiResponseError> {
  const detail = await readApiError(response);
  return new ApiResponseError({
    code: detail?.code,
    message: detail?.message ?? fallbackMessage,
    requestId:
      detail?.request_id ?? response.headers.get("x-request-id") ?? undefined,
    status: response.status,
  });
}

export async function readApiError(
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
    typeof value.error.code === "string" &&
    typeof value.error.message === "string" &&
    typeof value.error.request_id === "string"
  );
}
