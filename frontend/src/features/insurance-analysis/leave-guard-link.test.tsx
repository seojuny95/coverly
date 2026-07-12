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

  it("calls onLeave before navigating when confirmed", async () => {
    const user = userEvent.setup();
    const calls: string[] = [];
    const onLeave = vi.fn(() => calls.push("onLeave"));
    push.mockImplementation(() => calls.push("push"));
    render(
      <LeaveGuardLink href="/upload" enabled onLeave={onLeave}>
        업로드로
      </LeaveGuardLink>,
    );
    await user.click(screen.getByText("업로드로"));
    await user.click(screen.getByRole("button", { name: "나가기" }));
    expect(onLeave).toHaveBeenCalledTimes(1);
    expect(push).toHaveBeenCalledWith("/upload");
    expect(calls).toEqual(["onLeave", "push"]);
  });

  it("does not call onLeave when navigating directly (not enabled)", async () => {
    const user = userEvent.setup();
    const onLeave = vi.fn();
    render(
      <LeaveGuardLink href="/upload" enabled={false} onLeave={onLeave}>
        업로드로
      </LeaveGuardLink>,
    );
    await user.click(screen.getByText("업로드로"));
    expect(push).toHaveBeenCalledWith("/upload");
    expect(onLeave).not.toHaveBeenCalled();
  });
});
