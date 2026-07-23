import { apiResponseError, apiUrl } from "../../shared/api/client";
import {
  ApiRequestTimeoutError,
  PORTFOLIO_SESSION_REQUEST_TIMEOUT_MS,
  requestWithDeadline,
} from "../../shared/api/request";
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

export async function createPortfolioSession(
  signal?: AbortSignal,
): Promise<PortfolioSessionResult> {
  return requestSession("/portfolio/sessions", undefined, signal);
}

export async function refreshPortfolioSession(
  portfolioSessionToken: string,
  signal?: AbortSignal,
): Promise<PortfolioSessionResult> {
  return requestSession(
    "/portfolio/sessions/refresh",
    portfolioSessionToken,
    signal,
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
        timeoutMessage: "Portfolio session request timed out",
      },
    );
  } catch (error) {
    if (error instanceof ApiRequestTimeoutError) throw error;
    if (error instanceof Error && error.name === "AbortError") throw error;
    throw new Error("Portfolio session request failed");
  }

  if (!response.ok) {
    const error = await apiResponseError(
      response,
      "Portfolio session request failed",
    );
    const code = error.code;
    if (response.status === 403 || code === "INVALID_PORTFOLIO_SESSION") {
      throw new PortfolioSessionExpiredError();
    }
    throw error;
  }

  return response;
}
