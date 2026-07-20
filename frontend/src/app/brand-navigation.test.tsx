import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "../test/render-with-providers";
import { POLICY_RESULT_DEFAULTS } from "../test/api-fixtures";
import { BrandNavigation } from "./brand-navigation";

const navigation = vi.hoisted(() => ({
  pathname: "/",
  push: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => navigation.pathname,
  useRouter: () => ({ push: navigation.push }),
}));

describe("BrandNavigation", () => {
  it("renders a direct home link outside the analysis route", () => {
    navigation.pathname = "/upload";
    renderWithProviders(<BrandNavigation />);

    expect(screen.getByRole("link", { name: "Coverly AI 홈" })).toHaveAttribute(
      "href",
      "/",
    );
  });

  it("guards the home link when analysis data would be lost", async () => {
    navigation.pathname = "/analysis";
    const user = userEvent.setup();
    renderWithProviders(<BrandNavigation />, {
      initialAnalysis: {
        generatedAt: "2026-07-19T00:00:00.000Z",
        portfolioSessionToken: "test-token",
        portfolioSessionExpiresAt: "2030-01-01T00:00:00.000Z",
        counselTurnsRemaining: 10,
        insuranceDocuments: [
          {
            id: "policy-1",
            fileName: "policy.pdf",
            result: { ...POLICY_RESULT_DEFAULTS, 문자수: 1 },
          },
        ],
      },
    });

    await user.click(screen.getByRole("link", { name: "Coverly AI 홈" }));

    expect(
      screen.getByRole("alertdialog", {
        name: "지금 나가면 분석 내용이 지워져요",
      }),
    ).toBeInTheDocument();
    expect(navigation.push).not.toHaveBeenCalled();
  });
});
