import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { POLICY_RESULT_DEFAULTS } from "@/test/api-fixtures";
import * as errorReporting from "@/shared/api/errors";
import * as sessionApi from "./api";
import { mergeInsuranceAnalysis } from "./merge-analysis";
import {
  InsuranceDataProvider,
  useInsuranceData,
  type InsuranceAnalysis,
} from "./store";

function makeAnalysis(id: string): InsuranceAnalysis {
  return {
    generatedAt: "2026-07-12T00:00:00.000Z",
    portfolioSessionToken: "test-portfolio-token",
    portfolioSessionExpiresAt: "2030-01-01T00:00:00.000Z",
    counselTurnsRemaining: 10,
    insuranceDocuments: [
      { id, fileName: `${id}.pdf`, result: POLICY_RESULT_DEFAULTS },
    ],
  };
}

describe("InsuranceDataProvider", () => {
  beforeEach(() => vi.restoreAllMocks());

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
      portfolioSessionToken: "test-portfolio-token",
      portfolioSessionExpiresAt: "2030-01-01T00:00:00.000Z",
      counselTurnsRemaining: 10,
      insuranceDocuments: [
        {
          id: "a",
          fileName: "first.pdf",
          result: {
            ...POLICY_RESULT_DEFAULTS,
            status: "accepted",
            문자수: 1,
            기본정보: {
              ...POLICY_RESULT_DEFAULTS.기본정보,
              보험사: "삼성화재",
              증권번호: "POLICY-TEST-001",
            },
          },
        },
      ],
    };
    const next: InsuranceAnalysis = {
      generatedAt: "2026-07-12T01:00:00.000Z",
      portfolioSessionToken: "test-portfolio-token",
      portfolioSessionExpiresAt: "2030-01-01T00:00:00.000Z",
      counselTurnsRemaining: 10,
      insuranceDocuments: [
        {
          id: "b",
          fileName: "duplicate.pdf",
          result: {
            ...POLICY_RESULT_DEFAULTS,
            status: "accepted",
            문자수: 1,
            기본정보: {
              ...POLICY_RESULT_DEFAULTS.기본정보,
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
      portfolioSessionToken: "test-portfolio-token",
      portfolioSessionExpiresAt: "2030-01-01T00:00:00.000Z",
      counselTurnsRemaining: 10,
      insuranceDocuments: [
        {
          id: "a",
          fileName: "first.pdf",
          fileFingerprint: "abc123",
          result: {
            ...POLICY_RESULT_DEFAULTS,
            status: "accepted",
            문자수: 1,
            기본정보: {
              ...POLICY_RESULT_DEFAULTS.기본정보,
              피보험자: "테스트고객",
            },
          },
        },
      ],
    };
    const next: InsuranceAnalysis = {
      generatedAt: "2026-07-12T01:00:00.000Z",
      portfolioSessionToken: "test-portfolio-token",
      portfolioSessionExpiresAt: "2030-01-01T00:00:00.000Z",
      counselTurnsRemaining: 10,
      insuranceDocuments: [
        {
          id: "b",
          fileName: "duplicate.pdf",
          fileFingerprint: "abc123",
          result: {
            ...POLICY_RESULT_DEFAULTS,
            status: "accepted",
            문자수: 1,
            기본정보: {
              ...POLICY_RESULT_DEFAULTS.기본정보,
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
      portfolioSessionToken: "test-portfolio-token",
      portfolioSessionExpiresAt: "2030-01-01T00:00:00.000Z",
      counselTurnsRemaining: 10,
      insuranceDocuments: [
        {
          id: "a",
          fileName: "updated.pdf",
          result: { ...POLICY_RESULT_DEFAULTS, 문자수: 2 },
        },
      ],
    };

    expect(mergeInsuranceAnalysis(current, next).insuranceDocuments).toEqual([
      next.insuranceDocuments[0],
    ]);
  });

  it("releases an old identity when a document replacement changes policy", () => {
    const current: InsuranceAnalysis = {
      ...makeAnalysis("a"),
      insuranceDocuments: [
        {
          id: "a",
          fileName: "old.pdf",
          fileFingerprint: "old-policy",
          result: POLICY_RESULT_DEFAULTS,
        },
      ],
    };
    const replacement = {
      id: "a",
      fileName: "replacement.pdf",
      fileFingerprint: "replacement-policy",
      result: POLICY_RESULT_DEFAULTS,
    };
    const reusedOldIdentity = {
      id: "b",
      fileName: "old-policy-new-document.pdf",
      fileFingerprint: "old-policy",
      result: POLICY_RESULT_DEFAULTS,
    };
    const next: InsuranceAnalysis = {
      ...makeAnalysis("a"),
      insuranceDocuments: [replacement, reusedOldIdentity],
    };

    expect(mergeInsuranceAnalysis(current, next).insuranceDocuments).toEqual([
      replacement,
      reusedOldIdentity,
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

  it("reports a server session deletion failure without keeping local data", async () => {
    const failure = new Error("delete failed");
    vi.spyOn(sessionApi, "deletePortfolioSession").mockRejectedValue(failure);
    const reportFailure = vi
      .spyOn(errorReporting, "reportClientOperationFailure")
      .mockImplementation(() => undefined);
    const { result } = renderHook(() => useInsuranceData(), {
      wrapper: InsuranceDataProvider,
    });

    act(() => result.current.setAnalysis(makeAnalysis("a")));
    act(() => result.current.clear());

    expect(result.current.analysis).toBeNull();
    await waitFor(() => {
      expect(reportFailure).toHaveBeenCalledWith(
        "portfolio_session_delete",
        failure,
      );
    });
  });

  it("deletes the latest server session when the provider unmounts", async () => {
    const deleteSession = vi
      .spyOn(sessionApi, "deletePortfolioSession")
      .mockResolvedValue(undefined);
    const { result, unmount } = renderHook(() => useInsuranceData(), {
      wrapper: InsuranceDataProvider,
    });

    act(() => result.current.setAnalysis(makeAnalysis("a")));
    unmount();

    await waitFor(() => {
      expect(deleteSession).toHaveBeenCalledWith("test-portfolio-token");
    });
  });

  it("replaces the portfolio session token", () => {
    const { result } = renderHook(() => useInsuranceData(), {
      wrapper: InsuranceDataProvider,
    });
    act(() =>
      result.current.setAnalysis({
        generatedAt: "2026-07-12T00:00:00.000Z",
        portfolioSessionToken: "old-token",
        portfolioSessionExpiresAt: "invalid",
        counselTurnsRemaining: 10,
        insuranceDocuments: [],
      }),
    );

    act(() =>
      result.current.replacePortfolioSession({
        portfolioSessionToken: "new-token",
        expiresAt: "2030-01-01T00:15:00.000Z",
        counselTurnsRemaining: 10,
      }),
    );

    expect(result.current.analysis?.portfolioSessionToken).toBe("new-token");
    expect(result.current.analysis?.portfolioSessionExpiresAt).toBe(
      "2030-01-01T00:15:00.000Z",
    );
  });
});
