import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "../../test-utils/render-with-providers";
import type { AnalyzedInsurance } from "../insurance-analysis/insurance-analysis-store";
import { InsuranceChatbot } from "./insurance-chatbot";
import * as api from "./portfolio-api";

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

  it("shows a pending indicator then appends the answer", async () => {
    let resolveAnswer: ((value: api.QaAnswer) => void) | undefined;
    const pending = new Promise<api.QaAnswer>((resolve) => {
      resolveAnswer = resolve;
    });
    vi.spyOn(api, "askPortfolioQuestion").mockReturnValue(pending);
    const user = await openChat();

    await user.type(screen.getByLabelText("보험 질문"), "암 진단비는?");
    await user.click(screen.getByRole("button", { name: "질문하기" }));

    expect(
      await screen.findByText("증권에서 근거를 확인하고 있어요."),
    ).toBeInTheDocument();

    resolveAnswer?.({
      status: "answered",
      answer: "암 진단비는 1,000만원이에요.",
      citations: [],
      limitations: [],
      suggestions: ["다른 질문 있어요?"],
    });

    expect(
      await screen.findByText("암 진단비는 1,000만원이에요."),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("증권에서 근거를 확인하고 있어요."),
    ).not.toBeInTheDocument();
    expect(screen.getByText("다른 질문 있어요?")).toBeInTheDocument();
  });

  it("appends an error message when the request fails", async () => {
    vi.spyOn(api, "askPortfolioQuestion").mockRejectedValue(new Error("boom"));
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
