import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "../../test-utils/render-with-providers";
import type { AnalyzedInsurance } from "../insurance-analysis/insurance-analysis-store";
import { InsuranceChatbot } from "./insurance-chatbot";
import * as api from "./portfolio-api";

type StreamHandlers = Parameters<typeof api.streamPortfolioQuestion>[3];

const docs: AnalyzedInsurance[] = [
  { id: "1", fileName: "1.pdf", result: { status: "accepted", 문자수: 1 } },
];

async function openChat() {
  const user = userEvent.setup();
  renderWithProviders(<InsuranceChatbot documents={docs} />);
  await user.click(screen.getByRole("button", { name: "내 보험에 질문하기" }));
  return user;
}

describe("InsuranceChatbot", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("shows a pending indicator then streams the answer", async () => {
    let handlers: StreamHandlers | undefined;
    let resolveStream: (() => void) | undefined;
    vi.spyOn(api, "streamPortfolioQuestion").mockImplementation(
      (_question, _documents, _history, streamHandlers) => {
        handlers = streamHandlers;
        return new Promise<void>((resolve) => {
          resolveStream = resolve;
        });
      },
    );
    const user = await openChat();

    await user.type(screen.getByLabelText("보험 질문"), "암 진단비는?");
    await user.click(screen.getByRole("button", { name: "질문하기" }));

    expect(await screen.findByRole("status")).toBeInTheDocument();

    await act(async () => {
      handlers?.onDelta("암 진단비는 1,000만원이에요.");
      handlers?.onEnd({
        status: "answered",
        citations: [],
        limitations: [],
        suggestions: ["다른 질문 있어요?"],
      });
      resolveStream?.();
    });

    expect(
      await screen.findByText("암 진단비는 1,000만원이에요."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.getByText("다른 질문 있어요?")).toBeInTheDocument();
  });

  it("appends an error message when the request fails", async () => {
    vi.spyOn(api, "streamPortfolioQuestion").mockRejectedValue(
      new Error("boom"),
    );
    const user = await openChat();

    await user.type(screen.getByLabelText("보험 질문"), "암 진단비는?");
    await user.click(screen.getByRole("button", { name: "질문하기" }));

    expect(
      await screen.findByText(
        "답을 가져오지 못했어요. 대화 내용은 그대로 있으니 잠시 후 다시 질문해주세요.",
      ),
    ).toBeInTheDocument();
  });
});
