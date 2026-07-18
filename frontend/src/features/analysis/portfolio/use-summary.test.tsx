import { renderHook, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { makeTestQueryClient } from "../../../test/render-with-providers";
import { POLICY_RESULT_DEFAULTS } from "../../../test/api-fixtures";
import type { AnalyzedInsurance } from "../store";
import { usePortfolioSummary } from "./use-summary";
import * as api from "./api";

const docs: AnalyzedInsurance[] = [
  { id: "1", fileName: "1.pdf", result: POLICY_RESULT_DEFAULTS },
];
const deathBenefitContext: api.DeathBenefitGuideInput = {
  has_dependent_family: false,
  has_minor_children: false,
  has_major_debt: false,
};

describe("usePortfolioSummary", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("returns success state from the query", async () => {
    vi.spyOn(api, "requestPortfolioSummary").mockResolvedValue({
      classifications: [],
    } as unknown as api.PortfolioSummary);
    const client = makeTestQueryClient();
    const { result } = renderHook(
      () => usePortfolioSummary(docs, deathBenefitContext, "portfolio-token"),
      {
        wrapper: ({ children }) => (
          <QueryClientProvider client={client}>{children}</QueryClientProvider>
        ),
      },
    );
    await waitFor(() => expect(result.current.state.status).toBe("success"));
  });

  it("keeps the previous summary while death benefit context refreshes", async () => {
    const nextRequest = new Promise<api.PortfolioSummary>(() => undefined);
    const requestPortfolioSummary = vi
      .spyOn(api, "requestPortfolioSummary")
      .mockResolvedValueOnce({
        classifications: ["first"],
      } as unknown as api.PortfolioSummary)
      .mockReturnValueOnce(nextRequest);
    const client = makeTestQueryClient();
    const { result, rerender } = renderHook(
      ({ context }) => usePortfolioSummary(docs, context, "portfolio-token"),
      {
        initialProps: { context: deathBenefitContext },
        wrapper: ({ children }) => (
          <QueryClientProvider client={client}>{children}</QueryClientProvider>
        ),
      },
    );

    await waitFor(() => expect(result.current.state.status).toBe("success"));

    rerender({
      context: {
        ...deathBenefitContext,
        has_dependent_family: true,
      },
    });

    await waitFor(() =>
      expect(requestPortfolioSummary).toHaveBeenCalledTimes(2),
    );
    expect(result.current.state.status).toBe("success");
    expect(result.current.isRefreshing).toBe(true);
  });

  it("does not keep the previous summary when documents change", async () => {
    const nextRequest = new Promise<api.PortfolioSummary>(() => undefined);
    vi.spyOn(api, "requestPortfolioSummary")
      .mockResolvedValueOnce({
        classifications: ["first"],
      } as unknown as api.PortfolioSummary)
      .mockReturnValueOnce(nextRequest);
    const client = makeTestQueryClient();
    const { result, rerender } = renderHook(
      ({ documents }) =>
        usePortfolioSummary(documents, deathBenefitContext, "portfolio-token"),
      {
        initialProps: { documents: docs },
        wrapper: ({ children }) => (
          <QueryClientProvider client={client}>{children}</QueryClientProvider>
        ),
      },
    );

    await waitFor(() => expect(result.current.state.status).toBe("success"));

    rerender({
      documents: [
        ...docs,
        {
          id: "2",
          fileName: "2.pdf",
          result: { ...POLICY_RESULT_DEFAULTS, 문자수: 2 },
        } satisfies AnalyzedInsurance,
      ],
    });

    expect(result.current.state.status).toBe("loading");
    expect(result.current.isRefreshing).toBe(false);
  });
});
