import { apiResponseError, apiUrl } from "../../shared/api/client";
import {
  AppRequestError,
  GENERIC_REQUEST_ERROR_MESSAGE,
} from "../../shared/api/errors";
import {
  ApiRequestTimeoutError,
  PORTFOLIO_SESSION_REQUEST_TIMEOUT_MS,
  requestWithDeadline,
} from "../../shared/api/request";
import { waitForBackendReady } from "../../shared/api/readiness";
import {
  isTransientRequestError,
  retryOperation,
} from "../../shared/api/retry";
import type {
  PortfolioSessionDocumentsDeleteRequest,
  PortfolioSessionRequest,
  PortfolioSessionResponse,
} from "../../shared/api/contracts";

export type PortfolioSessionResult = PortfolioSessionResponse;

type SessionPath =
  | "/portfolio/sessions"
  | "/portfolio/sessions/refresh"
  | "/portfolio/sessions/delete"
  | "/portfolio/sessions/documents/delete";

type SessionRequestBody =
  PortfolioSessionRequest | PortfolioSessionDocumentsDeleteRequest;

export class PortfolioSessionExpiredError extends Error {
  constructor() {
    super("Portfolio session expired");
    this.name = "PortfolioSessionExpiredError";
  }
}

export class PortfolioSessionRequestError extends AppRequestError {
  constructor(cause?: unknown) {
    super({
      cause,
      developerMessage: "Portfolio session request failed",
      name: "PortfolioSessionRequestError",
      userMessage: GENERIC_REQUEST_ERROR_MESSAGE,
    });
  }
}

export async function createPortfolioSession(
  signal?: AbortSignal,
): Promise<PortfolioSessionResult> {
  return requestSession("/portfolio/sessions", undefined, signal);
}

export async function refreshPortfolioSession(
  portfolioSessionToken: string,
  signal?: AbortSignal,
): Promise<PortfolioSessionResult> {
  return retryOperation(
    () =>
      requestSession(
        "/portfolio/sessions/refresh",
        portfolioSessionToken,
        signal,
      ),
    {
      maxAttempts: 2,
      signal,
      shouldRetry: (error) =>
        error instanceof PortfolioSessionRequestError ||
        isTransientRequestError(error),
      beforeRetry: () => waitForBackendReady({ signal }),
    },
  );
}

export async function deletePortfolioSession(
  portfolioSessionToken: string,
  signal?: AbortSignal,
): Promise<void> {
  await request(
    "/portfolio/sessions/delete",
    portfolioSessionToken,
    undefined,
    signal,
  );
}

export async function deletePortfolioSessionDocuments(
  portfolioSessionToken: string,
  documentIds: string[],
  signal?: AbortSignal,
): Promise<void> {
  if (documentIds.length === 0) return;
  await request(
    "/portfolio/sessions/documents/delete",
    undefined,
    {
      portfolioSessionToken,
      documentIds,
    } satisfies PortfolioSessionDocumentsDeleteRequest,
    signal,
  );
}

async function requestSession(
  path: SessionPath,
  token?: string,
  signal?: AbortSignal,
): Promise<PortfolioSessionResult> {
  const response = await request(path, token, undefined, signal);
  return (await response.json()) as PortfolioSessionResult;
}

async function request(
  path: SessionPath,
  token?: string,
  explicitBody?: SessionRequestBody,
  signal?: AbortSignal,
): Promise<Response> {
  let response: Response;
  try {
    const body =
      explicitBody ??
      (token
        ? ({ portfolioSessionToken: token } satisfies PortfolioSessionRequest)
        : undefined);
    response = await requestWithDeadline(
      apiUrl(path),
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: body ? JSON.stringify(body) : undefined,
      },
      {
        signal,
        timeoutMs: PORTFOLIO_SESSION_REQUEST_TIMEOUT_MS,
        timeoutMessage:
          "분석 세션을 확인하는 시간이 길어지고 있어요. 잠시 후 다시 시도해주세요.",
      },
    );
  } catch (error) {
    if (error instanceof ApiRequestTimeoutError) throw error;
    if (error instanceof Error && error.name === "AbortError") throw error;
    throw new PortfolioSessionRequestError(error);
  }

  if (!response.ok) {
    const error = await apiResponseError(
      response,
      GENERIC_REQUEST_ERROR_MESSAGE,
    );
    const code = error.code;
    if (response.status === 403 || code === "INVALID_PORTFOLIO_SESSION") {
      throw new PortfolioSessionExpiredError();
    }
    throw error;
  }

  return response;
}
