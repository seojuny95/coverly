import { describe, expect, it } from "vitest";
import type { AnalyzedInsurance } from "../store";
import { portfolioKey } from "./query-key";

const doc = (id: string, 문자수: number): AnalyzedInsurance =>
  ({ id, result: { 문자수 } }) as unknown as AnalyzedInsurance;

describe("portfolioKey", () => {
  it("is empty for no documents", () => {
    expect(portfolioKey([])).toBe("");
  });

  it("joins id:문자수 per document", () => {
    expect(portfolioKey([doc("a", 10), doc("b", 20)])).toBe("a:10|b:20");
  });

  it("changes when any document's content length changes", () => {
    const before = portfolioKey([doc("a", 10), doc("b", 20)]);
    const after = portfolioKey([doc("a", 10), doc("b", 21)]);
    expect(after).not.toBe(before);
  });
});
