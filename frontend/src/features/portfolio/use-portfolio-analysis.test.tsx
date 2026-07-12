import { renderHook, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { makeTestQueryClient } from "../../test-utils/render-with-providers";
import type { AnalyzedInsurance } from "../insurance-analysis/insurance-analysis-store";
import { usePortfolioAnalysis } from "./use-portfolio-analysis";
import * as api from "./portfolio-api";

const covered: AnalyzedInsurance = {
  id: "1",
  fileName: "1.pdf",
  result: {
    status: "accepted",
    문자수: 10,
    보장목록: [{ 담보명: "암", 가입금액: "1", 보장내용: null, 해설: null }],
  },
};

describe("usePortfolioAnalysis", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("requests analysis once for eligible docs + demographics", async () => {
    const spy = vi.spyOn(api, "requestPortfolioAnalysis").mockResolvedValue({
      status: "complete",
    } as unknown as api.PortfolioAnalysisResult);
    const client = makeTestQueryClient();
    const { result } = renderHook(
      () => usePortfolioAnalysis([covered], { age: 35, gender: "남성" }),
      {
        wrapper: ({ children }) => (
          <QueryClientProvider client={client}>{children}</QueryClientProvider>
        ),
      },
    );
    await waitFor(() => expect(result.current.status).toBe("success"));
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it("refetches when a non-eligible document's content changes", async () => {
    // auto insurance is excluded from `eligible`, but requestPortfolioAnalysis
    // still sends the full document set — so a change confined to this
    // non-eligible document must still bust the cache key.
    const auto = (문자수: number): AnalyzedInsurance => ({
      id: "auto-1",
      fileName: "auto.pdf",
      result: {
        status: "accepted",
        문자수,
        기본정보: { 보험분류: "자동차" },
      },
    });
    const spy = vi.spyOn(api, "requestPortfolioAnalysis").mockResolvedValue({
      status: "complete",
    } as unknown as api.PortfolioAnalysisResult);
    const client = makeTestQueryClient();
    const { result, rerender } = renderHook(
      ({ documents }) =>
        usePortfolioAnalysis(documents, { age: 35, gender: "남성" }),
      {
        initialProps: { documents: [covered, auto(5)] },
        wrapper: ({ children }) => (
          <QueryClientProvider client={client}>{children}</QueryClientProvider>
        ),
      },
    );
    await waitFor(() => expect(result.current.status).toBe("success"));
    expect(spy).toHaveBeenCalledTimes(1);

    rerender({ documents: [covered, auto(6)] });
    await waitFor(() => expect(spy).toHaveBeenCalledTimes(2));
  });

  it("stays idle without demographics", () => {
    const spy = vi.spyOn(api, "requestPortfolioAnalysis");
    const client = makeTestQueryClient();
    const { result } = renderHook(() => usePortfolioAnalysis([covered], null), {
      wrapper: ({ children }) => (
        <QueryClientProvider client={client}>{children}</QueryClientProvider>
      ),
    });
    expect(result.current.status).toBe("idle");
    expect(spy).not.toHaveBeenCalled();
  });
});
