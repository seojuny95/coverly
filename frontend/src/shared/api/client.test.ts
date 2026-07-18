import { describe, expect, it } from "vitest";
import { apiResponseError, apiUrl, readApiErrorPayload } from "./client";

describe("shared API client", () => {
  it("builds only paths declared by the generated contract", () => {
    expect(apiUrl("/policies/parse")).toBe(
      "http://localhost:8000/policies/parse",
    );
  });

  it("reads the backend error envelope", async () => {
    const result = await readApiErrorPayload(
      new Response(
        JSON.stringify({
          error: {
            code: "INVALID_PORTFOLIO_SESSION",
            message: "분석 세션이 만료됐어요.",
            request_id: "request-1",
          },
        }),
      ),
    );

    expect(result).toEqual({
      detail: {
        code: "INVALID_PORTFOLIO_SESSION",
        message: "분석 세션이 만료됐어요.",
        request_id: "request-1",
      },
      isJson: true,
    });
  });

  it("falls back safely when a response is outside the API contract", async () => {
    const error = await apiResponseError(
      new Response("Bad Gateway", {
        status: 502,
        headers: { "x-request-id": "request-2" },
      }),
      "요청에 실패했어요.",
    );

    expect(error).toMatchObject({
      code: undefined,
      message: "요청에 실패했어요.",
      requestId: "request-2",
      status: 502,
    });
  });

  it("rejects an unknown error code outside the generated contract", async () => {
    const result = await readApiErrorPayload(
      new Response(
        JSON.stringify({
          error: {
            code: "UNDECLARED_BACKEND_ERROR",
            message: "내부 세부 정보",
            request_id: "request-3",
          },
        }),
      ),
    );

    expect(result).toEqual({ detail: null, isJson: true });
  });
});
