export const PORTFOLIO_REQUEST_TIMEOUT_MS = 90 * 1000;
export const PORTFOLIO_SESSION_REQUEST_TIMEOUT_MS = 15 * 1000;

export class ApiRequestTimeoutError extends Error {
  readonly code = "REQUEST_TIMEOUT";

  constructor(message: string) {
    super(message);
    this.name = "ApiRequestTimeoutError";
  }
}

type RequestWithDeadlineOptions = {
  signal?: AbortSignal;
  timeoutMs: number;
  timeoutMessage: string;
};

export async function requestWithDeadline(
  input: RequestInfo | URL,
  init: RequestInit,
  { signal, timeoutMs, timeoutMessage }: RequestWithDeadlineOptions,
): Promise<Response> {
  const controller = new AbortController();
  let abortSource: "caller" | "timeout" | null = null;

  const timeoutId = setTimeout(() => {
    if (abortSource) return;
    abortSource = "timeout";
    controller.abort();
  }, timeoutMs);

  const abortFromCaller = () => {
    if (abortSource) return;
    abortSource = "caller";
    clearTimeout(timeoutId);
    controller.abort(signal?.reason);
  };
  if (signal?.aborted) {
    abortFromCaller();
  } else {
    signal?.addEventListener("abort", abortFromCaller, { once: true });
  }

  try {
    return await fetch(input, { ...init, signal: controller.signal });
  } catch (error) {
    if (abortSource === "timeout") {
      throw new ApiRequestTimeoutError(timeoutMessage);
    }
    throw error;
  } finally {
    clearTimeout(timeoutId);
    signal?.removeEventListener("abort", abortFromCaller);
  }
}
