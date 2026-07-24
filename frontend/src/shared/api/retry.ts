import { ApiResponseError } from "./client";
import { ApiRequestTimeoutError } from "./request";

const RETRYABLE_HTTP_STATUSES = new Set([408, 425, 429, 502, 503, 504]);
const DEFAULT_BASE_DELAY_MS = 750;
const DEFAULT_MAX_DELAY_MS = 5000;
const MAX_SERVER_RETRY_AFTER_MS = 5 * 60 * 1000;

type RetryOperationOptions = {
  maxAttempts: number;
  signal?: AbortSignal;
  shouldRetry?: (error: unknown) => boolean;
  beforeRetry?: (error: unknown, nextAttempt: number) => Promise<void>;
  baseDelayMs?: number;
  maxDelayMs?: number;
};

export function isTransientRequestError(error: unknown): boolean {
  if (error instanceof ApiResponseError) {
    return RETRYABLE_HTTP_STATUSES.has(error.status);
  }
  return error instanceof ApiRequestTimeoutError || error instanceof TypeError;
}

export async function retryOperation<T>(
  operation: (attempt: number) => Promise<T>,
  {
    maxAttempts,
    signal,
    shouldRetry = isTransientRequestError,
    beforeRetry,
    baseDelayMs = DEFAULT_BASE_DELAY_MS,
    maxDelayMs = DEFAULT_MAX_DELAY_MS,
  }: RetryOperationOptions,
): Promise<T> {
  if (!Number.isInteger(maxAttempts) || maxAttempts < 1) {
    throw new RangeError("maxAttempts must be a positive integer");
  }

  for (let attempt = 1; ; attempt += 1) {
    throwIfAborted(signal);
    try {
      return await operation(attempt);
    } catch (error) {
      if (attempt >= maxAttempts || !shouldRetry(error)) throw error;

      await wait(retryDelay(error, attempt, baseDelayMs, maxDelayMs), signal);
      if (beforeRetry) await beforeRetry(error, attempt + 1);
    }
  }
}

function retryDelay(
  error: unknown,
  attempt: number,
  baseDelayMs: number,
  maxDelayMs: number,
): number {
  const retryAfterMs = readRetryAfterMs(error);
  if (retryAfterMs !== undefined) {
    return Math.min(retryAfterMs, MAX_SERVER_RETRY_AFTER_MS);
  }

  const exponentialDelay = Math.min(
    maxDelayMs,
    baseDelayMs * 2 ** (attempt - 1),
  );
  const jitter = 0.8 + Math.random() * 0.4;
  return Math.round(exponentialDelay * jitter);
}

function readRetryAfterMs(error: unknown): number | undefined {
  if (typeof error !== "object" || error === null) return undefined;
  if (!("retryAfterMs" in error)) return undefined;
  const value = error.retryAfterMs;
  return typeof value === "number" && Number.isFinite(value) && value >= 0
    ? value
    : undefined;
}

function wait(delayMs: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
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

function abortReason(signal?: AbortSignal): unknown {
  return signal?.reason ?? new DOMException("Aborted", "AbortError");
}
