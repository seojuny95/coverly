import { renderHook, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { makeTestQueryClient } from "../../test-utils/render-with-providers";
import type { AnalyzedInsurance } from "../insurance-analysis/insurance-analysis-store";
import { usePortfolioSummary } from "./use-portfolio-summary";
import * as api from "./portfolio-api";

const docs: AnalyzedInsurance[] = [
  { id: "1", fileName: "1.pdf", result: { status: "accepted", 문자수: 1 } },
];

describe("usePortfolioSummary", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("returns success state from the query", async () => {
    vi.spyOn(api, "requestPortfolioSummary").mockResolvedValue({
      classifications: [],
    } as unknown as api.PortfolioSummary);
    const client = makeTestQueryClient();
    const { result } = renderHook(() => usePortfolioSummary(docs), {
      wrapper: ({ children }) => (
        <QueryClientProvider client={client}>{children}</QueryClientProvider>
      ),
    });
    await waitFor(() => expect(result.current.state.status).toBe("success"));
  });
});
