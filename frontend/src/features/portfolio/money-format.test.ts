import { describe, expect, it } from "vitest";
import { formatKoreanWon, formatWon } from "./money-format";

describe("formatKoreanWon", () => {
  it("returns a placeholder for non-finite amounts", () => {
    expect(formatKoreanWon(NaN)).toBe("금액 확인 필요");
    expect(formatKoreanWon(Infinity)).toBe("금액 확인 필요");
  });

  it("returns 0원 for zero", () => {
    expect(formatKoreanWon(0)).toBe("0원");
  });

  it("breaks amounts into 억/만/천/원 parts", () => {
    expect(formatKoreanWon(50_000)).toBe("5만원");
    expect(formatKoreanWon(120_000_000)).toBe("1억 2,000만원");
    expect(formatKoreanWon(1_500)).toBe("1천원 500원");
  });

  it("prefixes a minus sign for negative amounts", () => {
    expect(formatKoreanWon(-30_000)).toBe("-3만원");
  });
});

describe("formatWon", () => {
  it("renders a plain comma-separated won amount", () => {
    expect(formatWon(30_000)).toBe("30,000원");
    expect(formatWon(0)).toBe("0원");
  });
});
