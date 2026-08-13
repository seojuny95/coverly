import { render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import GlobalErrorBoundary from "./global-error";

describe("global error boundary logging", () => {
  afterEach(() => {
    vi.restoreAllMocks();
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
