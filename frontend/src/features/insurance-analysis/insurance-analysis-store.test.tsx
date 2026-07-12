import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
  InsuranceDataProvider,
  mergeInsuranceAnalysis,
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

  it("does not add another document with the same policy identity", () => {
    const current: InsuranceAnalysis = {
      generatedAt: "2026-07-12T00:00:00.000Z",
      insuranceDocuments: [
        {
          id: "a",
          fileName: "first.pdf",
          result: {
            status: "accepted",
            문자수: 1,
            기본정보: {
              보험사: "삼성화재",
              증권번호: "POLICY-TEST-001",
            },
          },
        },
      ],
    };
    const next: InsuranceAnalysis = {
      generatedAt: "2026-07-12T01:00:00.000Z",
      insuranceDocuments: [
        {
          id: "b",
          fileName: "duplicate.pdf",
          result: {
            status: "accepted",
            문자수: 1,
            기본정보: {
              보험사: "삼성 화재",
              증권번호: "policy-test-001",
            },
          },
        },
      ],
    };

    expect(mergeInsuranceAnalysis(current, next).insuranceDocuments).toEqual([
      current.insuranceDocuments[0],
    ]);
  });

  it("does not add another document with the same file fingerprint", () => {
    const current: InsuranceAnalysis = {
      generatedAt: "2026-07-12T00:00:00.000Z",
      insuranceDocuments: [
        {
          id: "a",
          fileName: "first.pdf",
          fileFingerprint: "abc123",
          result: {
            status: "accepted",
            문자수: 1,
            기본정보: {
              피보험자: "테스트고객",
            },
          },
        },
      ],
    };
    const next: InsuranceAnalysis = {
      generatedAt: "2026-07-12T01:00:00.000Z",
      insuranceDocuments: [
        {
          id: "b",
          fileName: "duplicate.pdf",
          fileFingerprint: "abc123",
          result: {
            status: "accepted",
            문자수: 1,
            기본정보: {
              피보험자: "테스트고객",
            },
          },
        },
      ],
    };

    expect(mergeInsuranceAnalysis(current, next).insuranceDocuments).toEqual([
      current.insuranceDocuments[0],
    ]);
  });

  it("keeps later-wins behavior when the document id matches", () => {
    const current = makeAnalysis("a");
    const next: InsuranceAnalysis = {
      generatedAt: "2026-07-12T01:00:00.000Z",
      insuranceDocuments: [
        {
          id: "a",
          fileName: "updated.pdf",
          result: { status: "accepted", 문자수: 2 },
        },
      ],
    };

    expect(mergeInsuranceAnalysis(current, next).insuranceDocuments).toEqual([
      next.insuranceDocuments[0],
    ]);
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
