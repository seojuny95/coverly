const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type ApiErrorResponse = {
  error?: {
    code?: string;
  };
};

export type PortfolioSessionResult = {
  portfolioSessionToken: string;
  expiresAt: string;
};

export class PortfolioSessionExpiredError extends Error {
  constructor() {
    super("Portfolio session expired");
    this.name = "PortfolioSessionExpiredError";
  }
}

export async function createPortfolioSession(): Promise<PortfolioSessionResult> {
  return requestSession("");
}

export async function refreshPortfolioSession(
  portfolioSessionToken: string,
): Promise<PortfolioSessionResult> {
  return requestSession("/refresh", portfolioSessionToken);
}

export async function deletePortfolioSession(
  portfolioSessionToken: string,
): Promise<void> {
  await request("/delete", portfolioSessionToken);
}

async function requestSession(
  path: string,
  token?: string,
): Promise<PortfolioSessionResult> {
  const response = await request(path, token);
  return (await response.json()) as PortfolioSessionResult;
}

async function request(path: string, token?: string): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/portfolio/sessions${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: token
        ? JSON.stringify({ portfolioSessionToken: token })
        : undefined,
    });
  } catch {
    throw new Error("Portfolio session request failed");
  }

  if (!response.ok) {
    let code = "";
    try {
      const error = (await response.json()) as ApiErrorResponse;
      code = error.error?.code ?? "";
    } catch {
      // Non-JSON failures are transient server errors.
    }
    if (response.status === 403 || code === "INVALID_PORTFOLIO_SESSION") {
      throw new PortfolioSessionExpiredError();
    }
    throw new Error("Portfolio session request failed");
  }

  return response;
}
