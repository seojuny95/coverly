import { describe, expect, it } from "vitest";
import type { AnalyzedInsurance } from "../session/store";
import { POLICY_RESULT_DEFAULTS } from "@/test/api-fixtures";
import { portfolioKey } from "./query-key";

const doc = (
  id: string,
  insurer: string,
  fileFingerprint?: string,
): AnalyzedInsurance => ({
  id,
  fileName: `${id}.pdf`,
  fileFingerprint,
  result: {
    ...POLICY_RESULT_DEFAULTS,
    문자수: insurer.length,
    기본정보: { ...POLICY_RESULT_DEFAULTS.기본정보, 보험사: insurer },
  },
});

describe("portfolioKey", () => {
  it("is empty for no documents", () => {
    expect(portfolioKey([])).toBe("");
  });

  it("is stable when the same document set is reordered", () => {
    expect(portfolioKey([doc("a", "보험사A"), doc("b", "보험사B")])).toBe(
      portfolioKey([doc("b", "보험사B"), doc("a", "보험사A")]),
    );
  });

  it("changes when parsed content changes without changing its length", () => {
    const before = portfolioKey([doc("a", "보험사A")]);
    const after = portfolioKey([doc("a", "보험사B")]);
    expect(after).not.toBe(before);
  });

  it("changes when the uploaded file fingerprint changes", () => {
    const before = portfolioKey([doc("a", "보험사A", "file-a")]);
    const after = portfolioKey([doc("a", "보험사A", "file-b")]);
    expect(after).not.toBe(before);
  });
});
