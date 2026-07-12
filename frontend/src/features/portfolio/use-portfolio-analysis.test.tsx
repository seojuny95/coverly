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
