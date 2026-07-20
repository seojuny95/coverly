import { describe, expect, test, vi, beforeEach, afterEach } from "vitest";
import { act, renderHook } from "@testing-library/react";

import { useCompletionBeat } from "./use-completion-beat";

describe("useCompletionBeat", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  test("marks completing immediately and runs the action after the beat", () => {
    const action = vi.fn();
    const { result } = renderHook(() => useCompletionBeat());

    expect(result.current.isCompleting).toBe(false);

    act(() => result.current.runAfterBeat(action));
    expect(result.current.isCompleting).toBe(true);
    expect(action).not.toHaveBeenCalled();

    act(() => void vi.advanceTimersByTime(400));
    expect(action).toHaveBeenCalledOnce();
  });

  test("does not run the action after unmount", () => {
    const action = vi.fn();
    const { result, unmount } = renderHook(() => useCompletionBeat());

    act(() => result.current.runAfterBeat(action));
    unmount();
    act(() => void vi.advanceTimersByTime(400));

    expect(action).not.toHaveBeenCalled();
  });
});
