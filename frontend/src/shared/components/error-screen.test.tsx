import { render, screen, waitFor } from "@testing-library/react";
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
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(
        "화면을 다시 불러오지 못했어요.",
      ),
    );
    expect(
      screen.getByText(
        "잠시 후 다시 시도하거나 처음 화면에서 다시 시작해주세요.",
      ),
    ).toBeInTheDocument();
  });

  test("shows progress until an asynchronous retry settles", async () => {
    const user = userEvent.setup();
    let resolveRetry: (() => void) | undefined;
    const onRetry = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          resolveRetry = resolve;
        }),
    );
    render(<ErrorScreen onRetry={onRetry} />);

    await user.click(screen.getByRole("button", { name: "다시 시도하기" }));

    expect(
      screen.getByRole("button", { name: "다시 시도하는 중…" }),
    ).toBeDisabled();
    resolveRetry?.();

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(
        "화면을 다시 불러오지 못했어요.",
      ),
    );
  });
});
