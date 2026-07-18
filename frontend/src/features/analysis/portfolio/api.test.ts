import { afterEach, describe, expect, test, vi } from "vitest";
import type { AnalyzedInsurance } from "../store";
import { POLICY_RESULT_DEFAULTS } from "../../../test/api-fixtures";

import {
  prepareChatHistory,
  requestPortfolioSummary,
  streamPortfolioQuestion,
  type ChatHistoryItem,
} from "./api";

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
      기본정보: { 보험사: "브라우저에서 보내면 안 되는 보험사" },
      보장목록: [
        {
          담보명: "브라우저에서 보내면 안 되는 담보",
          가입금액: "1,000만원",
          보장내용: null,
          해설: null,
        },
      ],
    },
  },
];

describe("portfolio API preparation", () => {
  test("keeps only the latest 12 history messages", () => {
    const history: ChatHistoryItem[] = Array.from(
      { length: 15 },
      (_, index) => ({
        role: index % 2 === 0 ? "user" : "assistant",
        content: `message-${index}`,
      }),
    );

    const prepared = prepareChatHistory(history);

    expect(prepared).toHaveLength(12);
    expect(prepared[0].content).toBe("message-3");
    expect(prepared[11].content).toBe("message-14");
  });

  test("leaves history content limits to the API contract", () => {
    const longText = "가".repeat(1_200);

    expect(
      prepareChatHistory([{ role: "user", content: longText }])[0].content,
    ).toBe(longText);
  });
});

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
    const question = "가".repeat(600);
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response('data: {"type":"end","status":"answered"}\n\n', {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      }),
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
  });
});
