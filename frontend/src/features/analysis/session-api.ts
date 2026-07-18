import { apiResponseError, apiUrl } from "../../shared/api/client";
import type {
  PortfolioSessionRequest,
  PortfolioSessionResponse,
} from "../../shared/api/contracts";

export type PortfolioSessionResult = PortfolioSessionResponse;

type SessionPath =
  | "/portfolio/sessions"
  | "/portfolio/sessions/refresh"
  | "/portfolio/sessions/delete";

export class PortfolioSessionExpiredError extends Error {
  constructor() {
    super("Portfolio session expired");
    this.name = "PortfolioSessionExpiredError";
  }
}

export async function createPortfolioSession(): Promise<PortfolioSessionResult> {
  return requestSession("/portfolio/sessions");
}

export async function refreshPortfolioSession(
  portfolioSessionToken: string,
): Promise<PortfolioSessionResult> {
  return requestSession("/portfolio/sessions/refresh", portfolioSessionToken);
}

export async function deletePortfolioSession(
  portfolioSessionToken: string,
): Promise<void> {
  await request("/portfolio/sessions/delete", portfolioSessionToken);
}

async function requestSession(
  path: SessionPath,
  token?: string,
): Promise<PortfolioSessionResult> {
  const response = await request(path, token);
  return (await response.json()) as PortfolioSessionResult;
}

async function request(path: SessionPath, token?: string): Promise<Response> {
  let response: Response;
  try {
    const body = token
      ? ({ portfolioSessionToken: token } satisfies PortfolioSessionRequest)
      : undefined;
    response = await fetch(apiUrl(path), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
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
