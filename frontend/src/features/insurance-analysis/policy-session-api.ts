const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type ApiErrorResponse = {
  error?: {
    code?: string;
    message?: string;
  };
};

export type PolicySessionRefreshResult = {
  문서세션ID: string;
  expiresAt: string;
};

export class PolicySessionExpiredError extends Error {
  constructor() {
    super("Policy session expired");
    this.name = "PolicySessionExpiredError";
  }
}

export async function refreshPolicySession(
  documentSessionId: string,
): Promise<PolicySessionRefreshResult> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/policies/sessions/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ 문서세션ID: documentSessionId }),
    });
  } catch {
    throw new Error("Policy session refresh failed");
  }

  if (!response.ok) {
    let code = "";
    try {
      const error = (await response.json()) as ApiErrorResponse;
      code = error.error?.code ?? "";
    } catch {
      // Non-JSON errors are treated as transient refresh failures.
    }
    if (response.status === 403 || code === "INVALID_POLICY_SESSION") {
      throw new PolicySessionExpiredError();
    }
    throw new Error("Policy session refresh failed");
  }

  return (await response.json()) as PolicySessionRefreshResult;
}
