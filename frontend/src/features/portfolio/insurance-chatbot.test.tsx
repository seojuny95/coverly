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
  await user.click(
    screen.getByRole("button", { name: "AI 상담사에게 질문하기" }),
  );
  return user;
}

describe("InsuranceChatbot", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("shows the analysis limitations in the initial message", async () => {
    await openChat();

    expect(
      screen.getByText(
        "자동차보험과 약관이 필요한 보상 판단은 답변에서 제외해요.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "보상 조건·면책·지급 가능성은 약관 근거 없이 판단하지 않습니다.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText("실손형 담보는 가입금액 합계에 포함하지 않았습니다."),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "지급유형 또는 금액이 확인되지 않은 담보는 합계에 포함하지 않았습니다.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText("손해보험은 보장금 합계에 포함하지 않았어요."),
    ).toBeInTheDocument();
  });

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
      handlers?.onProgress?.({
        stage: "portfolio_facts",
        text: "올려주신 증권의 가입 담보를 확인하고 있어요.",
      });
    });

    expect(
      await screen.findByText("올려주신 증권의 가입 담보를 확인하고 있어요."),
    ).toBeInTheDocument();

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
    expect(
      screen.queryByText("올려주신 증권의 가입 담보를 확인하고 있어요."),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.getByText("다른 질문 있어요?")).toBeInTheDocument();
  });

  it("shows at most three answer sources", async () => {
    vi.spyOn(api, "streamPortfolioQuestion").mockImplementation(
      async (_question, _documents, _history, handlers) => {
        handlers.onDelta("확인한 보장을 정리했어요.");
        handlers.onEnd({
          status: "answered",
          citations: ["암", "뇌", "심장", "수술"].map((coverage_name) => ({
            insurer: "테스트보험",
            coverage_name,
          })),
          limitations: [],
          suggestions: [],
        });
      },
    );
    const user = await openChat();

    await user.type(screen.getByLabelText("보험 질문"), "보장을 알려줘");
    await user.click(screen.getByRole("button", { name: "질문하기" }));

    expect(await screen.findByText("테스트보험 · 암")).toBeInTheDocument();
    expect(screen.getByText("테스트보험 · 뇌")).toBeInTheDocument();
    expect(screen.getByText("테스트보험 · 심장")).toBeInTheDocument();
    expect(screen.queryByText("테스트보험 · 수술")).not.toBeInTheDocument();
  });

  it("does not repeat initial-only limitations under answers", async () => {
    vi.spyOn(api, "streamPortfolioQuestion").mockImplementation(
      async (_question, _documents, _history, handlers) => {
        handlers.onDelta("확인한 내용을 답변했어요.");
        handlers.onEnd({
          status: "answered",
          citations: [],
          limitations: [
            "보상 조건·면책·지급 가능성은 약관 근거 없이 판단하지 않습니다.",
            "실손형 담보는 가입금액 합계에 포함하지 않았습니다.",
            "지급유형 또는 금액이 확인되지 않은 담보는 합계에 포함하지 않았습니다.",
            "손해보험은 보장금 합계에 포함하지 않았어요.",
            "이 답변에만 필요한 안내예요.",
          ],
          suggestions: [],
        });
      },
    );
    const user = await openChat();

    await user.type(screen.getByLabelText("보험 질문"), "확인해줘");
    await user.click(screen.getByRole("button", { name: "질문하기" }));

    expect(
      await screen.findByText("이 답변에만 필요한 안내예요."),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText(
        "보상 조건·면책·지급 가능성은 약관 근거 없이 판단하지 않습니다.",
      ),
    ).toHaveLength(1);
    expect(
      screen.getAllByText(
        "지급유형 또는 금액이 확인되지 않은 담보는 합계에 포함하지 않았습니다.",
      ),
    ).toHaveLength(1);
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

  it("opens the full 상담 tab from the floating chat", async () => {
    const onExpand = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(
      <InsuranceChatbot documents={docs} onExpand={onExpand} />,
    );

    await user.click(
      screen.getByRole("button", { name: "AI 상담사에게 질문하기" }),
    );
    await user.click(
      screen.getByRole("button", { name: "AI 보험 상담 탭에서 크게 보기" }),
    );

    expect(onExpand).toHaveBeenCalledOnce();
  });
});
