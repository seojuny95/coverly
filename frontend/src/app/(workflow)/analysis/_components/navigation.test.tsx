import { fireEvent, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/render-with-providers";
import { AnalysisNavigation } from "./navigation";

const chatbot = vi.hoisted(() => ({ preload: vi.fn() }));

vi.mock("@/features/analysis/chat/load-chatbot", () => ({
  preloadInsuranceChatbot: chatbot.preload,
}));

const navigation = vi.hoisted(() => ({ pathname: "/analysis" }));

vi.mock("next/navigation", () => ({
  usePathname: () => navigation.pathname,
}));

describe("AnalysisNavigation", () => {
  beforeEach(() => {
    navigation.pathname = "/analysis";
    chatbot.preload.mockClear();
  });

  it("uses route links and marks only the current page", () => {
    const { rerender } = renderWithProviders(<AnalysisNavigation />);

    expect(screen.getByRole("link", { name: "내 보험" })).toHaveAttribute(
      "href",
      "/analysis",
    );
    expect(screen.getByRole("link", { name: "보험 분석" })).toHaveAttribute(
      "href",
      "/analysis/coverage",
    );
    expect(screen.getByRole("link", { name: "AI 보험 상담" })).toHaveAttribute(
      "href",
      "/analysis/chat",
    );
    expect(screen.getByRole("link", { name: "내 보험" })).toHaveAttribute(
      "aria-current",
      "page",
    );

    navigation.pathname = "/analysis/chat";
    rerender(<AnalysisNavigation />);

    expect(screen.getByRole("link", { name: "AI 보험 상담" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByRole("link", { name: "내 보험" })).not.toHaveAttribute(
      "aria-current",
    );
  });

  it("preloads the chatbot when the counseling tab receives intent", () => {
    renderWithProviders(<AnalysisNavigation />);
    const chatLink = screen.getByRole("link", { name: "AI 보험 상담" });

    fireEvent.mouseEnter(chatLink);
    fireEvent.focus(chatLink);

    expect(chatbot.preload).toHaveBeenCalledTimes(2);
  });
});
