import { afterEach, describe, expect, test, vi } from "vitest";
import type { AnalyzedInsurance } from "../store";
import { POLICY_RESULT_DEFAULTS } from "../../../test/api-fixtures";

import { requestPortfolioSummary, streamPortfolioQuestion } from "./api";

afterEach(() => {
  vi.restoreAllMocks();
});

const sessionDocuments: AnalyzedInsurance[] = [
  {
    id: "document-1",
    fileName: "policy.pdf",
    result: {
      ...POLICY_RESULT_DEFAULTS,
      status: "accepted",
      문자수: 10,
      기본정보: {
        보험사: "브라우저에서 보내면 안 되는 보험사",
        보험분류: "제3보험",
        상품태그: [],
      },
      보장목록: [
        {
          담보명: "브라우저에서 보내면 안 되는 담보",
          가입금액: "1,000만원",
          가입금액상태: "confirmed",
          보장내용: null,
          해설: null,
          설명근거: "none",
          유형: "담보",
        },
      ],
    },
  },
];

describe("portfolio session requests", () => {
  test("sends only the token and selected document ids for analysis", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          totals: [],
          actual_loss_coverages: [],
          excluded_coverages: [],
          excluded_auto_policy_count: 0,
        }),
        { status: 200 },
      ),
    );

    await requestPortfolioSummary(
      sessionDocuments,
      {
        has_dependent_family: false,
        has_minor_children: false,
        has_major_debt: false,
      },
      "portfolio-token",
    );

    const body = JSON.parse(
      String(fetchMock.mock.calls[0]?.[1]?.body),
    ) as Record<string, unknown>;
    expect(body).toMatchObject({
      portfolioSessionToken: "portfolio-token",
      policyIds: ["document-1"],
    });
    expect(body).not.toHaveProperty("policies");
  });

  test("does not resend structured policies to QA", async () => {
    const question = "가".repeat(400);
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        sseResponse([
          { type: "meta", status: "answered", generation: "fallback" },
          endEvent(),
        ]),
      );

    await streamPortfolioQuestion(
      question,
      sessionDocuments,
      [],
      { onDelta: vi.fn(), onEnd: vi.fn() },
      "portfolio-token",
    );

    const body = JSON.parse(
      String(fetchMock.mock.calls[0]?.[1]?.body),
    ) as Record<string, unknown>;
    expect(body).toMatchObject({
      question,
      portfolioSessionToken: "portfolio-token",
      policyIds: ["document-1"],
    });
    expect(body).not.toHaveProperty("policies");
    expect(body).not.toHaveProperty("demographics");
  });

  test("validates and dispatches fragmented SSE events through the terminal end", async () => {
    const encoder = new TextEncoder();
    const chunks = [
      'data: {"type":"progress","stage":"portfolio",',
      '"text":"확인 중"}\r\n\r\ndata: {"type":"meta","status":"answered","generation":"fallback"}\r\n\r\n',
      'data: {"type":"delta","text":"답변"}\n\n',
      `data: ${JSON.stringify(endEvent())}\n\n`,
    ];
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        new ReadableStream({
          start(controller) {
            for (const chunk of chunks)
              controller.enqueue(encoder.encode(chunk));
            controller.close();
          },
        }),
        { headers: { "Content-Type": "text/event-stream" } },
      ),
    );
    const onProgress = vi.fn();
    const onDelta = vi.fn();
    const onEnd = vi.fn();

    await streamPortfolioQuestion(
      "보험을 알려줘",
      sessionDocuments,
      [],
      { onProgress, onDelta, onEnd },
      "portfolio-token",
    );

    expect(onProgress).toHaveBeenCalledWith({
      type: "progress",
      stage: "portfolio",
      text: "확인 중",
    });
    expect(onDelta).toHaveBeenCalledWith("답변");
    expect(onEnd).toHaveBeenCalledWith(endEvent());
  });

  test("rejects a malformed SSE event instead of trusting its discriminator", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        [
          `data: ${JSON.stringify({ type: "meta", status: "answered", generation: "fallback" })}`,
          `data: ${JSON.stringify({ ...endEvent(), suggestions: "not-an-array" })}`,
          "",
        ].join("\n\n"),
        { headers: { "Content-Type": "text/event-stream" } },
      ),
    );

    await expect(
      streamPortfolioQuestion(
        "보험을 알려줘",
        sessionDocuments,
        [],
        { onDelta: vi.fn(), onEnd: vi.fn() },
        "portfolio-token",
      ),
    ).rejects.toThrow("상담 응답 형식을 확인할 수 없어요.");
  });

  test("rejects nested SSE data that violates the generated OpenAPI schema", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      sseResponse([
        { type: "meta", status: "answered", generation: "fallback" },
        {
          ...endEvent(),
          citations: [
            {
              policy_id: null,
              insurer: null,
              product_name: null,
              source_page: 0,
            },
          ],
        },
      ]),
    );

    await expect(
      streamPortfolioQuestion(
        "보험을 알려줘",
        sessionDocuments,
        [],
        { onDelta: vi.fn(), onEnd: vi.fn() },
        "portfolio-token",
      ),
    ).rejects.toThrow("상담 응답 형식을 확인할 수 없어요.");
  });

  test("rejects a stream that closes without a terminal end event", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      sseResponse([
        { type: "meta", status: "answered", generation: "fallback" },
        { type: "delta", text: "미완성 답변" },
      ]),
    );

    await expect(
      streamPortfolioQuestion(
        "보험을 알려줘",
        sessionDocuments,
        [],
        { onDelta: vi.fn(), onEnd: vi.fn() },
        "portfolio-token",
      ),
    ).rejects.toThrow("상담 응답 형식을 확인할 수 없어요.");
  });

  test("finishes at the terminal end even when the server keeps the connection open", async () => {
    const encoder = new TextEncoder();
    const cancel = vi.fn();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        new ReadableStream({
          start(controller) {
            controller.enqueue(
              encoder.encode(
                [
                  `data: ${JSON.stringify({ type: "meta", status: "answered", generation: "fallback" })}`,
                  `data: ${JSON.stringify(endEvent())}`,
                  "",
                ].join("\n\n"),
              ),
            );
          },
          cancel,
        }),
        { headers: { "Content-Type": "text/event-stream" } },
      ),
    );

    await streamPortfolioQuestion(
      "보험을 알려줘",
      sessionDocuments,
      [],
      { onDelta: vi.fn(), onEnd: vi.fn() },
      "portfolio-token",
    );

    expect(cancel).toHaveBeenCalledOnce();
  });
});

function endEvent() {
  return {
    type: "end" as const,
    status: "answered" as const,
    generation: "fallback" as const,
    citations: [],
    limitations: [],
    suggestions: [],
    claim_channels: null,
  };
}

function sseResponse(events: object[]) {
  return new Response(
    `${events.map((event) => `data: ${JSON.stringify(event)}`).join("\n\n")}\n\n`,
    {
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
    },
  );
}
