import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "../../../test/render-with-providers";
import { POLICY_RESULT_DEFAULTS } from "../../../test/api-fixtures";
import { PersistentChatbot } from "./persistent-chatbot";

const navigation = vi.hoisted(() => ({
  pathname: "/analysis",
  push: vi.fn(),
}));
const chatbotRender = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  usePathname: () => navigation.pathname,
  useRouter: () => ({ push: navigation.push }),
}));

vi.mock("./chatbot", () => ({
  InsuranceChatbot: (props: { mode: "floating" | "full" }) => {
    chatbotRender(props);
    return <div data-testid="insurance-chatbot">{props.mode}</div>;
  },
}));

const initialAnalysis = {
  generatedAt: "2026-08-14T00:00:00.000Z",
  portfolioSessionToken: "test-portfolio-token",
  portfolioSessionExpiresAt: "2030-01-01T00:00:00.000Z",
  counselTurnsRemaining: 10,
  insuranceDocuments: [
    {
      id: "policy-1",
      fileName: "policy.pdf",
      result: { ...POLICY_RESULT_DEFAULTS, 문자수: 1 },
    },
  ],
};

describe("PersistentChatbot", () => {
  beforeEach(() => {
    navigation.pathname = "/analysis";
    navigation.push.mockReset();
    chatbotRender.mockClear();
  });

  it("loads the chatbot only after the floating launcher is opened", async () => {
    const user = userEvent.setup();
    renderWithProviders(<PersistentChatbot />, { initialAnalysis });

    expect(
      screen.getByRole("button", { name: "AI 상담사에게 질문하기" }),
    ).toBeInTheDocument();
    expect(chatbotRender).not.toHaveBeenCalled();

    await user.click(
      screen.getByRole("button", { name: "AI 상담사에게 질문하기" }),
    );

    expect(await screen.findByTestId("insurance-chatbot")).toHaveTextContent(
      "floating",
    );
  });

  it("loads the full chatbot immediately on the chat route", async () => {
    navigation.pathname = "/analysis/chat";
    renderWithProviders(<PersistentChatbot />, { initialAnalysis });

    expect(await screen.findByTestId("insurance-chatbot")).toHaveTextContent(
      "full",
    );
  });

  it("keeps the chatbot mounted after leaving the chat route", async () => {
    const { rerender } = renderWithProviders(<PersistentChatbot />, {
      initialAnalysis,
    });

    navigation.pathname = "/analysis/chat";
    rerender(<PersistentChatbot />);
    expect(await screen.findByTestId("insurance-chatbot")).toHaveTextContent(
      "full",
    );

    navigation.pathname = "/analysis/coverage";
    rerender(<PersistentChatbot />);

    expect(screen.getByTestId("insurance-chatbot")).toHaveTextContent(
      "floating",
    );
  });
});
