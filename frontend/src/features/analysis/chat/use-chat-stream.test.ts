import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useChatStream } from "./use-chat-stream";
import * as api from "./api";

type StreamHandlers = Parameters<typeof api.streamPortfolioQuestion>[2];

describe("useChatStream", () => {
  beforeEach(() => vi.useFakeTimers());

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("combines deltas that arrive within one render interval", async () => {
    let handlers: StreamHandlers | undefined;
    vi.spyOn(api, "streamPortfolioQuestion").mockImplementation(
      (_question, _history, streamHandlers) => {
        handlers = streamHandlers;
        return new Promise<void>(() => undefined);
      },
    );
    const callbacks = createCallbacks();
    const { result } = renderHook(() => useChatStream(callbacks));

    act(() => {
      result.current.startStream(createRequest(), vi.fn());
      handlers?.onDelta("보험");
      handlers?.onDelta("료를 확인했어요.");
    });

    expect(callbacks.onDelta).not.toHaveBeenCalled();
    await act(() => vi.advanceTimersByTimeAsync(50));
    expect(callbacks.onDelta).toHaveBeenCalledOnce();
    expect(callbacks.onDelta).toHaveBeenCalledWith(7, "보험료를 확인했어요.");
  });

  it("flushes the remaining delta before completing", () => {
    let handlers: StreamHandlers | undefined;
    vi.spyOn(api, "streamPortfolioQuestion").mockImplementation(
      (_question, _history, streamHandlers) => {
        handlers = streamHandlers;
        return new Promise<void>(() => undefined);
      },
    );
    const callbacks = createCallbacks();
    const { result } = renderHook(() => useChatStream(callbacks));

    act(() => {
      result.current.startStream(createRequest(), vi.fn());
      handlers?.onDelta("마지막 답변");
      handlers?.onEnd();
    });

    expect(callbacks.onDelta).toHaveBeenCalledWith(7, "마지막 답변");
    expect(callbacks.onCompleted).toHaveBeenCalledOnce();
    expect(callbacks.onDelta.mock.invocationCallOrder[0]).toBeLessThan(
      callbacks.onCompleted.mock.invocationCallOrder[0],
    );
  });

  it("drops a pending batch when the hook unmounts", async () => {
    let handlers: StreamHandlers | undefined;
    let signal: AbortSignal | undefined;
    vi.spyOn(api, "streamPortfolioQuestion").mockImplementation(
      (_question, _history, streamHandlers, _token, requestSignal) => {
        handlers = streamHandlers;
        signal = requestSignal;
        return new Promise<void>(() => undefined);
      },
    );
    const callbacks = createCallbacks();
    const { result, unmount } = renderHook(() => useChatStream(callbacks));

    act(() => {
      result.current.startStream(createRequest(), vi.fn());
      handlers?.onDelta("표시하면 안 되는 답변");
    });
    unmount();
    await vi.advanceTimersByTimeAsync(50);

    expect(callbacks.onDelta).not.toHaveBeenCalled();
    expect(signal?.aborted).toBe(true);
  });
});

function createCallbacks() {
  return {
    portfolioSessionToken: "portfolio-token",
    onDelta: vi.fn(),
    onTurnsChanged: vi.fn(),
    onCompleted: vi.fn(),
    onFailed: vi.fn(),
  };
}

function createRequest() {
  return {
    question: "보험료는 얼마야?",
    history: [],
    assistantId: 7,
  };
}
