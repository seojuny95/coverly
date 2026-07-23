import { act, renderHook, waitFor } from "@testing-library/react";
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
const summaryWithoutOverview = {
  totals: [],
  actual_loss_coverages: [],
  excluded_coverages: [],
  excluded_auto_policy_count: 0,
} satisfies api.PortfolioSummary;
const generatedOverview = {
  generation: "llm" as const,
  title: "확인된 보장을 기준으로 총평을 정리했어요",
  paragraphs: ["확인된 보장 정보만 사용해 총평을 만들었어요."],
} satisfies api.PortfolioOverview;

describe("usePortfolioSummary", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(api, "requestPortfolioOverview").mockResolvedValue(
      generatedOverview,
    );
  });

  it("returns success state from the query", async () => {
    vi.spyOn(api, "requestPortfolioSummary").mockResolvedValue(
      summaryWithoutOverview,
    );
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
        ...summaryWithoutOverview,
        overview: {
          generation: "llm",
          title: "첫 총평",
          paragraphs: ["첫 총평 문장"],
        },
      })
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
        ...summaryWithoutOverview,
        overview: {
          generation: "llm",
          title: "첫 총평",
          paragraphs: ["첫 총평 문장"],
        },
      })
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

  it("exposes a retrying state while an error is requested again", async () => {
    let resolveRetry: ((summary: api.PortfolioSummary) => void) | undefined;
    const retryRequest = new Promise<api.PortfolioSummary>((resolve) => {
      resolveRetry = resolve;
    });
    vi.spyOn(api, "requestPortfolioSummary")
      .mockRejectedValueOnce(new Error("offline"))
      .mockReturnValueOnce(retryRequest);
    const client = makeTestQueryClient();
    const { result } = renderHook(
      () => usePortfolioSummary(docs, deathBenefitContext, "portfolio-token"),
      {
        wrapper: ({ children }) => (
          <QueryClientProvider client={client}>{children}</QueryClientProvider>
        ),
      },
    );

    await waitFor(() => expect(result.current.state.status).toBe("error"));

    let retryPromise: Promise<void> | undefined;
    act(() => {
      retryPromise = result.current.retry();
    });

    await waitFor(() => expect(result.current.isRetrying).toBe(true));

    resolveRetry?.(summaryWithoutOverview);
    await act(async () => {
      await retryPromise;
    });

    expect(result.current.state.status).toBe("success");
    expect(result.current.isRetrying).toBe(false);
    expect(result.current.overviewRetryFailed).toBe(false);
  });

  it("generates a missing overview through a separate request and merges it", async () => {
    vi.spyOn(api, "requestPortfolioSummary").mockResolvedValue(
      summaryWithoutOverview,
    );
    const requestPortfolioOverview = vi.spyOn(api, "requestPortfolioOverview");
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
    await waitFor(() =>
      expect(requestPortfolioOverview).toHaveBeenCalledOnce(),
    );

    expect(result.current.state).toEqual({
      status: "success",
      summary: { ...summaryWithoutOverview, overview: generatedOverview },
    });
  });

  it("keeps summary content visible when overview generation fails", async () => {
    vi.spyOn(api, "requestPortfolioSummary").mockResolvedValue(
      summaryWithoutOverview,
    );
    vi.spyOn(api, "requestPortfolioOverview").mockRejectedValue(
      new Error("offline"),
    );
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
    await waitFor(() => expect(result.current.overviewRetryFailed).toBe(true));

    expect(result.current.state).toEqual({
      status: "success",
      summary: summaryWithoutOverview,
    });
  });

  it("keeps previous summary content visible when a refresh fails", async () => {
    vi.spyOn(api, "requestPortfolioSummary")
      .mockResolvedValueOnce({
        ...summaryWithoutOverview,
        overview: generatedOverview,
      })
      .mockRejectedValueOnce(new Error("offline"));
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

    await act(async () => {
      await result.current.retry();
    });

    expect(result.current.state.status).toBe("success");
    expect(result.current.retryFailed).toBe(false);
  });

  it("reports when a manual retry also fails", async () => {
    vi.spyOn(api, "requestPortfolioSummary").mockRejectedValue(
      new Error("offline"),
    );
    const client = makeTestQueryClient();
    const { result } = renderHook(
      () => usePortfolioSummary(docs, deathBenefitContext, "portfolio-token"),
      {
        wrapper: ({ children }) => (
          <QueryClientProvider client={client}>{children}</QueryClientProvider>
        ),
      },
    );

    await waitFor(() => expect(result.current.state.status).toBe("error"));

    await act(async () => {
      await result.current.retry();
    });

    expect(result.current.state.status).toBe("error");
    expect(result.current.retryFailed).toBe(true);
  });

  it("ignores the outcome of an older retry after the query key changes", async () => {
    let resolveOldRetry: ((summary: api.PortfolioSummary) => void) | undefined;
    const oldRetryRequest = new Promise<api.PortfolioSummary>((resolve) => {
      resolveOldRetry = resolve;
    });
    vi.spyOn(api, "requestPortfolioSummary")
      .mockRejectedValueOnce(new Error("offline"))
      .mockReturnValueOnce(oldRetryRequest)
      .mockRejectedValueOnce(new Error("offline"));
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

    await waitFor(() => expect(result.current.state.status).toBe("error"));

    let oldRetryPromise: Promise<void> | undefined;
    act(() => {
      oldRetryPromise = result.current.retry();
    });
    await waitFor(() => expect(result.current.isRetrying).toBe(true));

    rerender({
      context: {
        ...deathBenefitContext,
        has_dependent_family: true,
      },
    });

    await waitFor(() => expect(result.current.state.status).toBe("error"));
    expect(result.current.isRetrying).toBe(false);

    resolveOldRetry?.(summaryWithoutOverview);
    await act(async () => {
      await oldRetryPromise;
    });

    expect(result.current.overviewRetryFailed).toBe(false);
    expect(result.current.retryFailed).toBe(false);
  });
});
