import { describe, expect, test } from "vitest";

import {
  normalizeQuestion,
  prepareChatHistory,
  type ChatHistoryItem,
} from "./portfolio-api";

describe("portfolio API limits", () => {
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

  test("caps history content and questions at backend limits", () => {
    const longText = "가".repeat(1_200);

    expect(
      prepareChatHistory([{ role: "user", content: longText }])[0].content,
    ).toHaveLength(1_000);
    expect(normalizeQuestion(`  ${longText}  `)).toHaveLength(500);
  });
});
