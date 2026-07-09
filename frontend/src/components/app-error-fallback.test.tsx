import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import { AppErrorFallback } from "./app-error-fallback";

describe("AppErrorFallback", () => {
  test("shows a safe recovery message without raw error details", () => {
    render(<AppErrorFallback digest="digest-123" />);

    expect(screen.getByText("화면을 불러오지 못했습니다.")).toBeInTheDocument();
    expect(screen.getByText("오류 ID: digest-123")).toBeInTheDocument();
    expect(screen.queryByText("Traceback")).not.toBeInTheDocument();
  });

  test("calls retry when the user clicks the retry button", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    render(<AppErrorFallback onRetry={onRetry} />);

    await user.click(screen.getByRole("button", { name: "다시 시도" }));

    expect(onRetry).toHaveBeenCalledOnce();
  });
});
