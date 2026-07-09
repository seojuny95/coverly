import { afterEach, describe, expect, test, vi } from "vitest";

import { UploadPolicyError, uploadPolicy } from "./upload-policy";

const policyFile = new File(["%PDF-1.7"], "policy.pdf", {
  type: "application/pdf",
});

describe("uploadPolicy", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  test("posts the selected file to the parse endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          status: "accepted",
          문자수: 32,
          문서판정: { 보험증권추정: true, 점수: 7, 근거: ["보험증권"] },
        }),
        { status: 200 },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await uploadPolicy(policyFile);

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/policies/parse",
      {
        method: "POST",
        body: expect.any(FormData),
      },
    );
    expect(result.문서판정.근거).toEqual(["보험증권"]);
  });

  test("throws a typed user-facing error when the parse endpoint rejects the file", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: {
              code: "POLICY_DOCUMENT_NOT_DETECTED",
              message: "보험증권으로 확인할 수 없습니다.",
              request_id: "req_123",
            },
          }),
          {
            status: 422,
          },
        ),
      ),
    );

    await expect(uploadPolicy(policyFile)).rejects.toMatchObject({
      code: "POLICY_DOCUMENT_NOT_DETECTED",
      requestId: "req_123",
      status: 422,
      userMessage: "보험증권으로 확인할 수 없습니다.",
      message: "보험증권으로 확인할 수 없습니다.",
    });
  });

  test("does not expose unsafe backend details as the user-facing message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            detail: "Traceback: /tmp/raw-policy.pdf parse failed",
          }),
          { status: 500 },
        ),
      ),
    );

    await expect(uploadPolicy(policyFile)).rejects.toMatchObject({
      code: "UPLOAD_FAILED",
      status: 500,
      userMessage:
        "서버에서 업로드를 처리하지 못했습니다. 잠시 후 다시 시도해주세요.",
    });
  });

  test("uses a stable user-facing message for structured 500 responses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: {
              code: "PDF_PARSE_CRASHED",
              message: "worker timeout at /tmp/policy.pdf",
              request_id: "req_500",
            },
          }),
          { status: 500 },
        ),
      ),
    );

    await expect(uploadPolicy(policyFile)).rejects.toMatchObject({
      code: "PDF_PARSE_CRASHED",
      requestId: "req_500",
      status: 500,
      userMessage:
        "서버에서 업로드를 처리하지 못했습니다. 잠시 후 다시 시도해주세요.",
    });
  });

  test("throws a generic message when the backend error response is not JSON", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response("Internal Server Error", { status: 500 }),
        ),
    );

    const error = await uploadPolicy(policyFile).catch((err: unknown) => err);

    expect(error).toBeInstanceOf(UploadPolicyError);
    expect(error).toMatchObject({
      code: "UPLOAD_FAILED",
      status: 500,
      userMessage: "업로드에 실패했습니다.",
    });
  });

  test("throws a connection message when the backend cannot be reached", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new TypeError("Failed to fetch")),
    );

    await expect(uploadPolicy(policyFile)).rejects.toMatchObject({
      code: "UPLOAD_NETWORK_ERROR",
      userMessage: "서버에 연결할 수 없습니다. 잠시 후 다시 시도해주세요.",
    });
  });
});
