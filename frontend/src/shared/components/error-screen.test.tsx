import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import { ErrorScreen } from "./error-screen";

describe("ErrorScreen", () => {
  test("shows a safe recovery message without raw error details", () => {
    render(<ErrorScreen digest="digest-123" />);

    expect(screen.getByText("화면을 불러오지 못했어요.")).toBeInTheDocument();
    expect(screen.getByText("오류 ID: digest-123")).toBeInTheDocument();
    expect(screen.queryByText("Traceback")).not.toBeInTheDocument();
  });

  test("calls retry when the user clicks the retry button", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    render(<ErrorScreen onRetry={onRetry} />);

    await user.click(screen.getByRole("button", { name: "다시 시도하기" }));

    expect(onRetry).toHaveBeenCalledOnce();
  });
});
