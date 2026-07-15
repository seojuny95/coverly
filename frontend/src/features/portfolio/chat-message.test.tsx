import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ChatMessage, type ChatMessageData } from "./chat-message";
import type { ClaimChannelBlock } from "./portfolio-api";

function assistant(overrides: Partial<ChatMessageData> = {}): ChatMessageData {
  return { id: 1, role: "assistant", text: "", ...overrides };
}

describe("ChatMessage", () => {
  it("renders a user message as plain text", () => {
    render(
      <ChatMessage
        message={{ id: 1, role: "user", text: "겹치는 보장 있어?" }}
      />,
    );
    expect(screen.getByText("겹치는 보장 있어?")).toBeInTheDocument();
  });

  it("escapes raw HTML in assistant markdown (no script injection)", () => {
    const { container } = render(
      <ChatMessage
        message={assistant({
          text: "안녕하세요 <img src=x onerror=alert(1)> <b>bold</b>",
        })}
      />,
    );
    // react-markdown does not render raw HTML: no injected <img>/<b> elements,
    // the markup shows up as escaped text instead.
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("b")).toBeNull();
    expect(
      screen.getByText(/<img src=x onerror=alert\(1\)>/),
    ).toBeInTheDocument();
  });

  it("drops a javascript: link in markdown (renders without an href)", () => {
    const { container } = render(
      <ChatMessage
        message={assistant({ text: "[click](javascript:alert(1))" })}
      />,
    );
    // The link text still renders as an anchor (assert it exists so this isn't
    // a vacuous pass), but it carries no navigable href.
    const anchor = container.querySelector("a");
    expect(anchor).not.toBeNull();
    expect(anchor).toHaveTextContent("click");
    expect(anchor?.getAttribute("href")).toBeFalsy();
  });

  it("renders assistant markdown emphasis and lists", () => {
    const { container } = render(
      <ChatMessage
        message={assistant({
          text: "**암진단비**는 확인돼요.\n\n- 가입금액: **3,000만원**\n- 기준: 증권 근거",
        })}
      />,
    );

    expect(screen.getByText("암진단비")).toHaveClass("font-semibold");
    expect(container.querySelector("ul")).not.toBeNull();
    expect(screen.getByText(/가입금액:/)).toBeInTheDocument();
    expect(screen.getByText("3,000만원")).toHaveClass("font-semibold");
  });

  it("keeps a safe claim-channel link but downgrades an unsafe one to text", () => {
    const claimChannels: ClaimChannelBlock = {
      insurers: [
        {
          name: "삼성화재",
          customer_center: "1588-5114",
          links: [
            { label: "홈페이지", url: "https://samsungfire.com" },
            { label: "위험링크", url: "javascript:alert(1)" },
          ],
        },
      ],
      medical_indemnity: null,
    };
    render(
      <ChatMessage
        message={assistant({ text: "청구는 여기서요", claimChannels })}
      />,
    );

    const safeLink = screen.getByRole("link", { name: "홈페이지" });
    expect(safeLink).toHaveAttribute("href", "https://samsungfire.com");
    // The javascript: link is not a link at all — just its label text.
    expect(
      screen.queryByRole("link", { name: "위험링크" }),
    ).not.toBeInTheDocument();
    expect(screen.getByText("위험링크")).toBeInTheDocument();
  });

  it("renders answer sources in a collapsed disclosure", async () => {
    const user = userEvent.setup();
    render(
      <ChatMessage
        message={assistant({
          text: "확인한 답변이에요.",
          sources: [{ label: "테스트보험 · 암진단비" }],
        })}
      />,
    );

    const disclosure = screen.getByText("확인한 근거").closest("details");
    expect(disclosure).not.toHaveAttribute("open");

    await user.click(screen.getByText("확인한 근거"));

    expect(disclosure).toHaveAttribute("open");
  });
});
