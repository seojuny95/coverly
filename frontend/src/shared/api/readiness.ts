import { apiUrl } from "./client";
import { AppRequestError } from "./errors";
import { requestWithDeadline } from "./request";

export const BACKEND_READINESS_TIMEOUT_MS = 90 * 1000;
const READINESS_ATTEMPT_TIMEOUT_MS = 10 * 1000;
const READINESS_RETRY_DELAY_MS = 1500;

export const BACKEND_READINESS_ERROR_MESSAGE =
  "분석 서버를 준비하지 못했어요. 잠시 후 다시 시도해 주세요.";

export class BackendReadinessError extends AppRequestError {
  constructor() {
    super({
      developerMessage: "Backend readiness deadline exceeded",
      name: "BackendReadinessError",
      userMessage: BACKEND_READINESS_ERROR_MESSAGE,
    });
  }
}

type BackendReadinessOptions = {
  signal?: AbortSignal;
  timeoutMs?: number;
  attemptTimeoutMs?: number;
  retryDelayMs?: number;
};

export async function waitForBackendReady({
  signal,
  timeoutMs = BACKEND_READINESS_TIMEOUT_MS,
  attemptTimeoutMs = READINESS_ATTEMPT_TIMEOUT_MS,
  retryDelayMs = READINESS_RETRY_DELAY_MS,
}: BackendReadinessOptions = {}): Promise<void> {
  const deadline = Date.now() + timeoutMs;

  while (Date.now() < deadline) {
    let nextRetryDelayMs = retryDelayMs;
    throwIfAborted(signal);
    const remainingMs = deadline - Date.now();

    try {
      const response = await requestWithDeadline(
        apiUrl("/ready"),
        {
          method: "GET",
          headers: { Accept: "application/json" },
          cache: "no-store",
        },
        {
          signal,
          timeoutMs: Math.min(attemptTimeoutMs, remainingMs),
          timeoutMessage: BACKEND_READINESS_ERROR_MESSAGE,
        },
      );
      if (isPermanentReadinessFailure(response.status)) {
        throw new BackendReadinessError();
      }
      if (await isReadyResponse(response)) return;
      nextRetryDelayMs =
        retryAfterMilliseconds(response.headers.get("retry-after")) ??
        retryDelayMs;
    } catch (error) {
      if (error instanceof BackendReadinessError) throw error;
      throwIfAborted(signal);
    }

    const retryWaitMs = Math.min(nextRetryDelayMs, deadline - Date.now());
    if (retryWaitMs > 0) await wait(retryWaitMs, signal);
  }

  throw new BackendReadinessError();
}

function retryAfterMilliseconds(value: string | null): number | undefined {
  if (!value) return undefined;

  const seconds = Number(value);
  if (Number.isFinite(seconds) && seconds >= 0) return seconds * 1000;

  const retryAt = Date.parse(value);
  if (!Number.isFinite(retryAt)) return undefined;
  return Math.max(0, retryAt - Date.now());
}

function isPermanentReadinessFailure(status: number): boolean {
  return (
    status >= 400 &&
    status < 500 &&
    status !== 408 &&
    status !== 425 &&
    status !== 429
  );
}

async function isReadyResponse(response: Response) {
  if (!response.ok) return false;
  try {
    const payload: unknown = await response.json();
    return (
      typeof payload === "object" &&
      payload !== null &&
      "status" in payload &&
      payload.status === "ready"
    );
  } catch {
    return false;
  }
}

function wait(delayMs: number, signal?: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const timeout = setTimeout(() => {
      signal?.removeEventListener("abort", abort);
      resolve();
    }, delayMs);
    const abort = () => {
      clearTimeout(timeout);
      reject(abortReason(signal));
    };
    if (signal?.aborted) {
      abort();
      return;
    }
    signal?.addEventListener("abort", abort, { once: true });
  });
}

function throwIfAborted(signal?: AbortSignal): void {
  if (signal?.aborted) throw abortReason(signal);
}

function abortReason(signal?: AbortSignal) {
  return signal?.reason instanceof Error
    ? signal.reason
    : new DOMException("Aborted", "AbortError");
}
