import { afterEach, describe, expect, test, vi } from "vitest";

import { UploadInsuranceError, uploadInsurance } from "./api";

const insuranceFile = new File(["%PDF-1.7"], "insurance.pdf", {
  type: "application/pdf",
});

describe("uploadInsurance", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  test("posts the selected file to the parse endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          status: "accepted",
          documentId: "test-document-id",
          문자수: 32,
          기본정보: {
            보험사: "삼성화재",
            상품명: "건강보험",
            증권번호: "POLICY-TEST-001",
            보험분류: "제3보험",
            상품태그: ["질병보험"],
            납입기간: "20년납",
            만기일: "2027-01-01",
            보험기간: {
              시작일: "2026-01-01",
              종료일: "2027-01-01",
            },
            보험료: {
              금액: 120000,
              납입주기: "월납",
            },
          },
        }),
        { status: 200 },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await uploadInsurance({
      file: insuranceFile,
      portfolioSessionToken: "portfolio-token",
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/policies/parse",
      {
        method: "POST",
        body: expect.any(FormData),
      },
    );
    expect(result.기본정보?.보험사).toBe("삼성화재");
    expect(result.기본정보?.보험분류).toBe("제3보험");
  });

  test("includes the PDF password when one is provided", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: "accepted", 문자수: 32 }), {
        status: 200,
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await uploadInsurance({
      file: insuranceFile,
      password: "900101",
      portfolioSessionToken: "portfolio-token",
    });

    const body = fetchMock.mock.calls[0]?.[1]?.body;
    expect(body).toBeInstanceOf(FormData);
    expect((body as FormData).get("password")).toBe("900101");
  });

  test("includes one portfolio session token when provided", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          status: "accepted",
          documentId: "document-1",
          문자수: 32,
        }),
        { status: 200 },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await uploadInsurance({
      file: insuranceFile,
      portfolioSessionToken: "portfolio-token",
    });

    const body = fetchMock.mock.calls[0]?.[1]?.body as FormData;
    expect(body.get("portfolioSessionToken")).toBe("portfolio-token");
    expect(result.documentId).toBe("document-1");
  });

  test("throws a typed user-facing error when the parse endpoint rejects the file", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: {
              code: "POLICY_PARSE_FAILED",
              message: "파일을 분석할 수 없습니다.",
              request_id: "req_123",
            },
          }),
          {
            status: 422,
          },
        ),
      ),
    );

    await expect(
      uploadInsurance({
        file: insuranceFile,
        portfolioSessionToken: "portfolio-token",
      }),
    ).rejects.toMatchObject({
      code: "POLICY_PARSE_FAILED",
      requestId: "req_123",
      status: 422,
      userMessage: "파일을 분석할 수 없습니다.",
      message: "파일을 분석할 수 없습니다.",
    });
  });

  test("does not expose unsafe backend details as the user-facing message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            detail: "Traceback: /tmp/raw-insurance.pdf parse failed",
          }),
          { status: 500 },
        ),
      ),
    );

    await expect(
      uploadInsurance({
        file: insuranceFile,
        portfolioSessionToken: "portfolio-token",
      }),
    ).rejects.toMatchObject({
      code: "UPLOAD_FAILED",
      status: 500,
      userMessage:
        "서버에서 파일을 처리하지 못했어요. 잠시 후 다시 시도해주세요.",
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
              message: "worker timeout at /tmp/insurance.pdf",
              request_id: "req_500",
            },
          }),
          { status: 500 },
        ),
      ),
    );

    await expect(
      uploadInsurance({
        file: insuranceFile,
        portfolioSessionToken: "portfolio-token",
      }),
    ).rejects.toMatchObject({
      code: "PDF_PARSE_CRASHED",
      requestId: "req_500",
      status: 500,
      userMessage:
        "서버에서 파일을 처리하지 못했어요. 잠시 후 다시 시도해주세요.",
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

    const error = await uploadInsurance({
      file: insuranceFile,
      portfolioSessionToken: "portfolio-token",
    }).catch((err: unknown) => err);

    expect(error).toBeInstanceOf(UploadInsuranceError);
    expect(error).toMatchObject({
      code: "UPLOAD_FAILED",
      status: 500,
      userMessage: "업로드에 실패했어요. 잠시 후 다시 시도해주세요.",
    });
  });

  test("throws a connection message when the backend cannot be reached", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new TypeError("Failed to fetch")),
    );

    await expect(
      uploadInsurance({
        file: insuranceFile,
        portfolioSessionToken: "portfolio-token",
      }),
    ).rejects.toMatchObject({
      code: "UPLOAD_NETWORK_ERROR",
      userMessage: "서버에 연결하지 못했어요. 잠시 후 다시 시도해주세요.",
    });
  });
});
