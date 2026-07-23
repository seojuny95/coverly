import { render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ErrorBoundary from "./error";
import GlobalErrorBoundary from "./global-error";

describe("app error boundary logging", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("does not write the raw app error message to the console payload", async () => {
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);

    render(
      <ErrorBoundary
        error={Object.assign(new Error("policy-number-123"), {
          digest: "digest-123",
        })}
        reset={vi.fn()}
      />,
    );

    await waitFor(() =>
      expect(consoleError.mock.calls).toContainEqual([
        "app_render_error",
        { digest: "digest-123", name: "Error" },
      ]),
    );
    expect(JSON.stringify(consoleError.mock.calls)).not.toContain(
      "policy-number-123",
    );
  });

  it("does not write the raw global error message to the console payload", async () => {
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);

    render(
      <GlobalErrorBoundary
        error={Object.assign(new Error("phone-010-1234-5678"), {
          digest: "digest-456",
        })}
        reset={vi.fn()}
      />,
    );

    await waitFor(() =>
      expect(consoleError.mock.calls).toContainEqual([
        "global_render_error",
        { digest: "digest-456", name: "Error" },
      ]),
    );
    expect(JSON.stringify(consoleError.mock.calls)).not.toContain(
      "phone-010-1234-5678",
    );
  });
});
