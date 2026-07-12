import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
  InsuranceDataProvider,
  useInsuranceData,
  type InsuranceAnalysis,
} from "./insurance-analysis-store";

function makeAnalysis(id: string): InsuranceAnalysis {
  return {
    generatedAt: "2026-07-12T00:00:00.000Z",
    insuranceDocuments: [
      { id, fileName: `${id}.pdf`, result: { status: "accepted", 문자수: 1 } },
    ],
  };
}

describe("InsuranceDataProvider", () => {
  it("stores analysis in memory and reports hasData", () => {
    const { result } = renderHook(() => useInsuranceData(), {
      wrapper: InsuranceDataProvider,
    });
    expect(result.current.hasData).toBe(false);
    act(() => result.current.setAnalysis(makeAnalysis("a")));
    expect(result.current.hasData).toBe(true);
    expect(result.current.analysis?.insuranceDocuments).toHaveLength(1);
  });

  it("merges documents by id", () => {
    const { result } = renderHook(() => useInsuranceData(), {
      wrapper: InsuranceDataProvider,
    });
    act(() => result.current.setAnalysis(makeAnalysis("a")));
    act(() => result.current.mergeDocuments(makeAnalysis("b")));
    expect(result.current.analysis?.insuranceDocuments).toHaveLength(2);
    act(() => result.current.mergeDocuments(makeAnalysis("a")));
    expect(result.current.analysis?.insuranceDocuments).toHaveLength(2);
  });

  it("clears the analysis", () => {
    const { result } = renderHook(() => useInsuranceData(), {
      wrapper: InsuranceDataProvider,
    });
    act(() => result.current.setAnalysis(makeAnalysis("a")));
    expect(result.current.hasData).toBe(true);
    act(() => result.current.clear());
    expect(result.current.hasData).toBe(false);
    expect(result.current.analysis).toBeNull();
  });
});
