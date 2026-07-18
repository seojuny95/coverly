import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

import { LeaveGuardLink } from "./leave-guard-link";

describe("LeaveGuardLink", () => {
  it("asks before leaving when enabled and navigates on confirm", async () => {
    const user = userEvent.setup();
    render(
      <LeaveGuardLink href="/upload" enabled>
        업로드로
      </LeaveGuardLink>,
    );
    await user.click(screen.getByText("업로드로"));
    expect(push).not.toHaveBeenCalled();
    expect(screen.getByText(/지금 나가면/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "나가기" }));
    expect(push).toHaveBeenCalledWith("/upload");
  });

  it("navigates directly when not enabled", async () => {
    const user = userEvent.setup();
    render(
      <LeaveGuardLink href="/upload" enabled={false}>
        업로드로
      </LeaveGuardLink>,
    );
    await user.click(screen.getByText("업로드로"));
    expect(push).toHaveBeenCalledWith("/upload");
  });
});
