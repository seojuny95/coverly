import { describe, expect, test, vi, beforeEach, afterEach } from "vitest";
import { act, renderHook } from "@testing-library/react";

import { useCompletionDelay } from "./use-completion-delay";

describe("useCompletionDelay", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  test("runs the action after the completion beat", () => {
    const action = vi.fn();
    const { result } = renderHook(() => useCompletionDelay());

    act(() => result.current.runAfterDelay(action));
    expect(action).not.toHaveBeenCalled();

    act(() => void vi.advanceTimersByTime(400));
    expect(action).toHaveBeenCalledOnce();
  });

  test("does not run the action after unmount", () => {
    const action = vi.fn();
    const { result, unmount } = renderHook(() => useCompletionDelay());

    act(() => result.current.runAfterDelay(action));
    unmount();
    act(() => void vi.advanceTimersByTime(400));

    expect(action).not.toHaveBeenCalled();
  });

  test("does not schedule a new action after unmount", () => {
    const action = vi.fn();
    const { result, unmount } = renderHook(() => useCompletionDelay());

    unmount();
    act(() => result.current.runAfterDelay(action));
    act(() => void vi.advanceTimersByTime(400));

    expect(action).not.toHaveBeenCalled();
  });
});
