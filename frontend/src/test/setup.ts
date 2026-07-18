import "@testing-library/jest-dom/vitest";

// jsdom has no ResizeObserver; radix-ui primitives (e.g. RadioGroup) use it
// to measure the underlying bubble input, so tests need a no-op stand-in.
if (typeof globalThis.ResizeObserver === "undefined") {
  class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  globalThis.ResizeObserver =
    ResizeObserverStub as unknown as typeof ResizeObserver;
}
