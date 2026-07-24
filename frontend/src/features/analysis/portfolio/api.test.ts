import { afterEach, describe, expect, test, vi } from "vitest";
import type { AnalyzedInsurance } from "../store";
import { POLICY_RESULT_DEFAULTS } from "../../../test/api-fixtures";

import {
  requestPortfolioOverview,
  requestPortfolioSummary,
  streamPortfolioQuestion,
} from "./api";

afterEach(() => {
  vi.useRealTimers();
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

  test("retries a transient summary failure", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            error: {
              code: "portfolio_session_unavailable",
              message: "분석 세션을 준비하지 못했어요.",
              request_id: "request-1",
            },
          }),
          { status: 503, headers: { "Retry-After": "0" } },
        ),
      )
      .mockResolvedValueOnce(
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

    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  test("composes the caller cancellation signal for summary requests", async () => {
    const caller = new AbortController();
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
      caller.signal,
    );

    const signal = fetchMock.mock.calls[0]?.[1]?.signal;
    expect(signal).toBeInstanceOf(AbortSignal);
    expect(signal).not.toBe(caller.signal);
  });

  test("sends only the token and selected document ids for overview generation", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          generation: "llm",
          title: "확인된 보장을 기준으로 총평을 정리했어요",
          paragraphs: ["확인된 보장 정보만 사용해 총평을 만들었어요."],
        }),
        { status: 200 },
      ),
    );

    await requestPortfolioOverview(
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
    expect(fetchMock.mock.calls[0]?.[0]).toContain("/portfolio/overview");
    expect(body).toMatchObject({
      portfolioSessionToken: "portfolio-token",
      policyIds: ["document-1"],
    });
    expect(body).not.toHaveProperty("policies");
  });

  test("retries overview only when the server confirms no result was produced", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            error: {
              code: "portfolio_overview_unavailable",
              message: "총평을 생성하지 못했어요.",
              request_id: "request-1",
            },
          }),
          { status: 503, headers: { "Retry-After": "0" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            generation: "llm",
            title: "확인된 보장을 기준으로 총평을 정리했어요",
            paragraphs: ["확인된 보장 정보만 사용해 총평을 만들었어요."],
          }),
          { status: 200 },
        ),
      );

    await requestPortfolioOverview(
      sessionDocuments,
      {
        has_dependent_family: false,
        has_minor_children: false,
        has_major_debt: false,
      },
      "portfolio-token",
    );

    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  test("does not repeat overview generation after an ambiguous network failure", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockRejectedValue(new TypeError("Failed to fetch"));

    await expect(
      requestPortfolioOverview(
        sessionDocuments,
        {
          has_dependent_family: false,
          has_minor_children: false,
          has_major_debt: false,
        },
        "portfolio-token",
      ),
    ).rejects.toBeInstanceOf(TypeError);

    expect(fetchMock).toHaveBeenCalledOnce();
  });

  test("asks with the session token and history, never the structured policies", async () => {
    const question = "가".repeat(400);
    const history = [{ role: "user" as const, content: "이전 질문" }];
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(sseResponse([metaEvent(), endEvent()]));

    await streamPortfolioQuestion(
      question,
      history,
      { onDelta: vi.fn(), onEnd: vi.fn() },
      "portfolio-token",
    );

    const body = JSON.parse(
      String(fetchMock.mock.calls[0]?.[1]?.body),
    ) as Record<string, unknown>;
    expect(body).toEqual({ question, session_id: "portfolio-token", history });
  });

  test("validates and dispatches fragmented SSE events through the terminal end", async () => {
    const encoder = new TextEncoder();
    const chunks = [
      'data: {"type":"meta","in_scope":true,',
      '"answered_question":"보험을 알려줘","excluded_note":null,"turns_remaining":9}\r\n\r\n',
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
    const onMeta = vi.fn();
    const onDelta = vi.fn();
    const onEnd = vi.fn();

    await streamPortfolioQuestion(
      "보험을 알려줘",
      [],
      { onMeta, onDelta, onEnd },
      "portfolio-token",
    );

    expect(onMeta).toHaveBeenCalledWith(metaEvent());
    expect(onDelta).toHaveBeenCalledWith("답변");
    expect(onEnd).toHaveBeenCalledOnce();
  });

  test("surfaces a typed server failure without treating it as answer text", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      sseResponse([
        metaEvent(),
        {
          type: "error",
          code: "QA_STREAM_FAILED",
          message:
            "답을 가져오지 못했어요. 대화 내용은 그대로 있으니 잠시 후 다시 질문해주세요.",
          request_id: "request-1",
          retryable: true,
        },
      ]),
    );
    const onDelta = vi.fn();

    await expect(
      streamPortfolioQuestion(
        "보험을 알려줘",
        [],
        { onDelta, onEnd: vi.fn() },
        "portfolio-token",
      ),
    ).rejects.toMatchObject({
      name: "QaStreamResponseError",
      code: "QA_STREAM_FAILED",
      requestId: "request-1",
    });
    expect(onDelta).not.toHaveBeenCalled();
  });

  test("stops waiting when the server never opens the stream", async () => {
    vi.useFakeTimers();
    vi.spyOn(globalThis, "fetch").mockImplementation(
      (_input, init) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => {
            reject(init.signal?.reason);
          });
        }),
    );

    const request = streamPortfolioQuestion(
      "보험을 알려줘",
      [],
      { onDelta: vi.fn(), onEnd: vi.fn() },
      "portfolio-token",
    );
    const expectation = expect(request).rejects.toMatchObject({
      name: "QaStreamTimeoutError",
      userMessage:
        "답변을 기다리는 시간이 길어지고 있어요. 잠시 후 다시 질문해주세요.",
    });

    await vi.advanceTimersByTimeAsync(30 * 1000);
    await expectation;
  });

  test("stops a stream that becomes idle after opening", async () => {
    vi.useFakeTimers();
    const cancel = vi.fn();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(new ReadableStream({ cancel }), {
        headers: { "Content-Type": "text/event-stream" },
      }),
    );

    const request = streamPortfolioQuestion(
      "보험을 알려줘",
      [],
      { onDelta: vi.fn(), onEnd: vi.fn() },
      "portfolio-token",
    );
    const expectation = expect(request).rejects.toMatchObject({
      name: "QaStreamTimeoutError",
    });

    await vi.advanceTimersByTimeAsync(45 * 1000);
    await expectation;
    expect(cancel).toHaveBeenCalledOnce();
  });

  test("rejects a malformed SSE event instead of trusting its discriminator", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      sseResponse([metaEvent(), { type: "delta", text: 42 }]),
    );

    await expect(
      streamPortfolioQuestion(
        "보험을 알려줘",
        [],
        { onDelta: vi.fn(), onEnd: vi.fn() },
        "portfolio-token",
      ),
    ).rejects.toMatchObject({
      name: "QaStreamProtocolError",
      userMessage:
        "답변을 정상적으로 확인하지 못했어요. 잠시 후 다시 질문해주세요.",
    });
  });

  test("rejects an SSE event that omits a field the generated schema requires", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      sseResponse([{ type: "meta", in_scope: true }, endEvent()]),
    );

    await expect(
      streamPortfolioQuestion(
        "보험을 알려줘",
        [],
        { onDelta: vi.fn(), onEnd: vi.fn() },
        "portfolio-token",
      ),
    ).rejects.toMatchObject({
      name: "QaStreamProtocolError",
      userMessage:
        "답변을 정상적으로 확인하지 못했어요. 잠시 후 다시 질문해주세요.",
    });
  });

  test("rejects an answer that starts before the meta event", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      sseResponse([{ type: "delta", text: "먼저 온 답변" }, endEvent()]),
    );

    await expect(
      streamPortfolioQuestion(
        "보험을 알려줘",
        [],
        { onDelta: vi.fn(), onEnd: vi.fn() },
        "portfolio-token",
      ),
    ).rejects.toMatchObject({
      name: "QaStreamProtocolError",
      userMessage:
        "답변을 정상적으로 확인하지 못했어요. 잠시 후 다시 질문해주세요.",
    });
  });

  test("rejects a stream that closes without a terminal end event", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      sseResponse([metaEvent(), { type: "delta", text: "미완성 답변" }]),
    );

    await expect(
      streamPortfolioQuestion(
        "보험을 알려줘",
        [],
        { onDelta: vi.fn(), onEnd: vi.fn() },
        "portfolio-token",
      ),
    ).rejects.toMatchObject({
      name: "QaStreamProtocolError",
      userMessage:
        "답변을 정상적으로 확인하지 못했어요. 잠시 후 다시 질문해주세요.",
    });
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
                  `data: ${JSON.stringify(metaEvent())}`,
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
      [],
      { onDelta: vi.fn(), onEnd: vi.fn() },
      "portfolio-token",
    );

    expect(cancel).toHaveBeenCalledOnce();
  });
});

function metaEvent() {
  return {
    type: "meta" as const,
    in_scope: true,
    answered_question: "보험을 알려줘",
    excluded_note: null,
    turns_remaining: 9,
  };
}

function endEvent() {
  return { type: "end" as const };
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
