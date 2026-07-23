import { act, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "../../../test/render-with-providers";
import { InsuranceChatbot } from "./chatbot";
import * as api from "./api";
import { ApiResponseError } from "@/shared/api/client";

type StreamHandlers = Parameters<typeof api.streamPortfolioQuestion>[2];

async function openChat(
  props: Partial<Parameters<typeof InsuranceChatbot>[0]> = {},
) {
  const user = userEvent.setup();
  renderWithProviders(
    <InsuranceChatbot
      portfolioSessionToken="portfolio-token"
      turnsRemaining={10}
      {...props}
    />,
  );
  await user.click(
    screen.getByRole("button", { name: "AI 상담사에게 질문하기" }),
  );
  return user;
}

describe("InsuranceChatbot", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("keeps the full-tab conversation inside a scrollable panel", () => {
    renderWithProviders(
      <InsuranceChatbot
        portfolioSessionToken="portfolio-token"
        turnsRemaining={10}
        mode="full"
      />,
    );

    expect(
      screen.queryByRole("heading", { name: "AI 보험 상담" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText("올려주신 증권을 바탕으로 함께 살펴봐요"),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("log", { name: "보험 상담 대화" })).toHaveClass(
      "min-h-0",
      "overflow-y-auto",
    );
  });

  it("shows a pending indicator then streams the answer", async () => {
    let handlers: StreamHandlers | undefined;
    let resolveStream: (() => void) | undefined;
    vi.spyOn(api, "streamPortfolioQuestion").mockImplementation(
      (_question, _history, streamHandlers) => {
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
      handlers?.onEnd();
      resolveStream?.();
    });

    expect(
      await screen.findByText("암 진단비는 1,000만원이에요."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("offers the starter questions again once the answer finishes", async () => {
    vi.spyOn(api, "streamPortfolioQuestion").mockImplementation(
      async (_question, _history, handlers) => {
        handlers.onDelta("확인한 보장을 정리했어요.");
        handlers.onEnd();
      },
    );
    const user = await openChat();

    await user.type(screen.getByLabelText("보험 질문"), "보장을 알려줘");
    await user.click(screen.getByRole("button", { name: "질문하기" }));

    expect(
      await screen.findByRole("button", {
        name: "겹치는 보장이 있는지 봐줄래요?",
      }),
    ).toBeInTheDocument();
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

  it("reports an expired session when the qa request is rejected by the session boundary", async () => {
    const onSessionExpired = vi.fn();
    vi.spyOn(api, "streamPortfolioQuestion").mockRejectedValue(
      new ApiResponseError({
        code: "INVALID_PORTFOLIO_SESSION",
        message: "분석 세션이 만료됐어요. 보험증권을 다시 올려주세요.",
        status: 403,
      }),
    );
    const user = await openChat({ onSessionExpired });

    await user.type(screen.getByLabelText("보험 질문"), "암 진단비는?");
    await user.click(screen.getByRole("button", { name: "질문하기" }));

    expect(
      await screen.findByText(
        "분석 세션이 만료됐어요. 다시 분석하려면 보험증권을 다시 올려주세요.",
      ),
    ).toBeInTheDocument();
    expect(onSessionExpired).toHaveBeenCalledOnce();
  });

  it("passes an abort signal to the qa stream request", async () => {
    let signal: AbortSignal | undefined;
    vi.spyOn(api, "streamPortfolioQuestion").mockImplementation(
      (_question, _history, _handlers, _token, requestSignal) => {
        signal = requestSignal;
        return new Promise<void>(() => undefined);
      },
    );
    const user = await openChat();

    await user.type(screen.getByLabelText("보험 질문"), "암 진단비는?");
    await user.click(screen.getByRole("button", { name: "질문하기" }));

    expect(signal).toBeInstanceOf(AbortSignal);
    expect(signal?.aborted).toBe(false);
  });

  it("does not leave an empty loading answer when the floating chat is closed during a request", async () => {
    let rejectStream: ((error: unknown) => void) | undefined;
    vi.spyOn(api, "streamPortfolioQuestion").mockImplementation(
      () =>
        new Promise<void>((_resolve, reject) => {
          rejectStream = reject;
        }),
    );
    const user = await openChat();

    await user.type(screen.getByLabelText("보험 질문"), "암 진단비는?");
    await user.click(screen.getByRole("button", { name: "질문하기" }));
    await user.click(screen.getByRole("button", { name: "닫기" }));

    await act(async () => {
      rejectStream?.(new DOMException("Aborted", "AbortError"));
    });

    await user.click(
      screen.getByRole("button", { name: "AI 상담사에게 질문하기" }),
    );
    expect(await screen.findByText("질문을 중단했어요.")).toBeInTheDocument();
    expect(screen.queryByLabelText("답변 준비 중")).not.toBeInTheDocument();
  });

  it("opens the full 상담 tab from the floating chat", async () => {
    const onExpand = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(
      <InsuranceChatbot
        portfolioSessionToken="portfolio-token"
        turnsRemaining={10}
        onExpand={onExpand}
      />,
    );

    await user.click(
      screen.getByRole("button", { name: "AI 상담사에게 질문하기" }),
    );
    await user.click(
      screen.getByRole("button", { name: "AI 보험 상담 탭에서 크게 보기" }),
    );

    expect(onExpand).toHaveBeenCalledOnce();
  });

  it("lets focus leave the non-modal floating chat", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <>
        <InsuranceChatbot
          portfolioSessionToken="portfolio-token"
          turnsRemaining={10}
        />
        <button type="button">채팅 밖 작업</button>
      </>,
    );

    await user.click(
      screen.getByRole("button", { name: "AI 상담사에게 질문하기" }),
    );
    const dialog = screen.getByRole("dialog", { name: "내 보험 질문" });
    within(dialog).getByRole("button", { name: "질문하기" }).focus();
    await user.tab();

    expect(screen.getByRole("button", { name: "채팅 밖 작업" })).toHaveFocus();
  });
});

describe("InsuranceChatbot question limit", () => {
  it("locks the composer and explains why once no turns are left", () => {
    renderWithProviders(
      <InsuranceChatbot
        portfolioSessionToken="portfolio-token"
        turnsRemaining={0}
        mode="full"
      />,
    );

    expect(screen.getByLabelText("보험 질문")).toBeDisabled();
    expect(screen.getByRole("button", { name: "질문하기" })).toBeDisabled();
    expect(
      screen.getByText(/할 수 있는 질문을 모두 사용했어요/),
    ).toBeInTheDocument();
  });

  it("shows how many questions are left while turns remain", () => {
    renderWithProviders(
      <InsuranceChatbot
        portfolioSessionToken="portfolio-token"
        turnsRemaining={3}
        mode="full"
      />,
    );

    expect(screen.getByText("질문 3번 남음")).toBeInTheDocument();
    expect(screen.getByLabelText("보험 질문")).not.toBeDisabled();
  });
});
