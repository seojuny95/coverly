import { afterEach, describe, expect, test, vi } from "vitest";

import { uploadPolicy } from "./upload-policy";

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

  test("throws backend detail when the parse endpoint rejects the file", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ detail: "보험증권으로 확인할 수 없습니다." }),
          {
            status: 422,
          },
        ),
      ),
    );

    await expect(uploadPolicy(policyFile)).rejects.toThrow(
      "보험증권으로 확인할 수 없습니다.",
    );
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

    await expect(uploadPolicy(policyFile)).rejects.toThrow(
      "업로드에 실패했습니다.",
    );
  });

  test("throws a connection message when the backend cannot be reached", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new TypeError("Failed to fetch")),
    );

    await expect(uploadPolicy(policyFile)).rejects.toThrow(
      "서버에 연결할 수 없습니다. 백엔드 실행 상태를 확인해주세요.",
    );
  });
});
