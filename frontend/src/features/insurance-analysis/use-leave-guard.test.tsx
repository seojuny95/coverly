import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useBeforeUnloadGuard } from "./use-leave-guard";

describe("useBeforeUnloadGuard", () => {
  it("prevents unload only while enabled", () => {
    const add = vi.spyOn(window, "addEventListener");
    const remove = vi.spyOn(window, "removeEventListener");
    const { rerender, unmount } = renderHook(
      ({ enabled }) => useBeforeUnloadGuard(enabled),
      { initialProps: { enabled: true } },
    );
    expect(add).toHaveBeenCalledWith("beforeunload", expect.any(Function));

    const handler = add.mock.calls.find(
      (c) => c[0] === "beforeunload",
    )![1] as EventListener;
    const event = new Event("beforeunload", { cancelable: true });
    handler(event);
    expect(event.defaultPrevented).toBe(true);

    rerender({ enabled: false });
    expect(remove).toHaveBeenCalledWith("beforeunload", expect.any(Function));
    unmount();
  });
});
